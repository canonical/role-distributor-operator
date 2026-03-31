"""Cross-model integration tests for role-distributor charm."""

from __future__ import annotations

import contextlib
import json
import pathlib
import time

import jubilant
import yaml

DEPLOY_TIMEOUT = 15 * 60.0  # 15 minutes for machine charm deploys
SETTLE_TIMEOUT = 5 * 60.0  # 5 minutes for config/relation changes to settle


def _get_machine_ids(juju: jubilant.Juju, app: str) -> dict[str, str]:
    """Return a mapping of unit_name -> machine_id for all units of an app."""
    units = juju.status().get_units(app)
    return {name: unit.machine for name, unit in units.items()}


def _unit_has_status(
    status: jubilant.Status,
    app: str,
    unit_name: str,
    expected_current: str,
    expected_message: str | None = None,
) -> bool:
    """Check if a specific unit has the expected workload status."""
    units = status.get_units(app)
    unit = units.get(unit_name)
    if unit is None:
        return False
    if unit.workload_status.current != expected_current:
        return False
    return not (expected_message is not None and unit.workload_status.message != expected_message)


def _get_assignment(juju: jubilant.Juju, unit_name: str) -> dict | None:
    """Return the current assignment for a unit, or ``None`` if unavailable."""
    with contextlib.suppress(jubilant.CLIError, KeyError, json.JSONDecodeError):
        task = juju.run(unit_name, "get-assignment", wait=60)
        return json.loads(task.results["assignment"])
    return None


def _all_units_active_with_roles(
    status: jubilant.Status,
    app: str,
    expected: dict[str, str],
) -> bool:
    """Check that every unit in expected has ActiveStatus with the given roles message.

    Args:
        status: Current juju status.
        app: Application name.
        expected: Mapping of unit_name -> expected roles string (e.g. "control,compute").
    """
    units = status.get_units(app)
    for unit_name, roles_msg in expected.items():
        unit = units.get(unit_name)
        if unit is None:
            return False
        if not unit.is_active:
            return False
        if unit.workload_status.message != f"roles: {roles_msg}":
            return False
    return True


def _build_config(model_name: str, applications: dict) -> str:
    """Build an application-scoped role-mapping YAML config string."""
    return yaml.dump({model_name: applications})


def _set_machine_defaults(
    applications: dict,
    app_name: str,
    unit_machines: dict[str, str],
    roles: list[str],
    workload_params: dict | None = None,
) -> None:
    """Populate machine defaults for one application."""
    app_cfg = applications.setdefault(app_name, {})
    machines = app_cfg.setdefault("machines", {})
    for machine_id in unit_machines.values():
        entry = {"roles": list(roles)}
        if workload_params is not None:
            entry["workload-params"] = dict(workload_params)
        machines[machine_id] = entry


def _set_unit_override(
    applications: dict,
    app_name: str,
    unit_name: str,
    roles: list[str],
    workload_params: dict | None = None,
) -> None:
    """Populate a unit override for one application."""
    app_cfg = applications.setdefault(app_name, {})
    units = app_cfg.setdefault("units", {})
    entry = {"roles": list(roles)}
    if workload_params is not None:
        entry["workload-params"] = dict(workload_params)
    units[unit_name] = entry


def _get_offer_relation_ids(juju: jubilant.Juju) -> list[int]:
    """Get all relation IDs for cross-model offers from ``juju offers``."""
    raw = juju.cli("offers", "--format", "json")
    offers_data = json.loads(raw)
    ids = []
    for offer_info in offers_data.values():
        for conn in offer_info.get("connections", []):
            if "relation-id" in conn:
                ids.append(int(conn["relation-id"]))
    return ids


def _offer_exists(juju: jubilant.Juju, offer_url: str) -> bool:
    """Return whether a specific CMR offer is still present."""
    raw = juju.cli("offers", "--format", "json")
    offers_data = json.loads(raw)
    return offer_url in offers_data


class TestCrossModel:
    """Cross-model integration tests, executed in order."""

    def test_deploy_and_relate_cross_model(
        self,
        charm: pathlib.Path,
        dummy_charm: pathlib.Path,
        provider_model: jubilant.Juju,
        requirer_model: jubilant.Juju,
    ):
        """Deploy both charms cross-model and establish relations."""
        # Deploy provider
        provider_model.deploy(f"./{charm}")
        provider_model.wait(
            lambda s: jubilant.all_blocked(s, "role-distributor"),
            timeout=DEPLOY_TIMEOUT,
        )

        # Deploy two requirer apps
        requirer_model.deploy(f"./{dummy_charm}", app="app-a", num_units=2)
        requirer_model.deploy(f"./{dummy_charm}", app="app-b", num_units=1)
        requirer_model.wait(
            lambda s: jubilant.all_waiting(s, "app-a") and jubilant.all_waiting(s, "app-b"),
            timeout=DEPLOY_TIMEOUT,
        )

        # Wire cross-model relation
        provider_name = provider_model.status().model.name
        provider_model.offer(
            f"{provider_name}.role-distributor",
            endpoint="role-assignment",
        )
        requirer_model.consume(f"{provider_name}.role-distributor")
        requirer_model.integrate("app-a", "role-distributor")
        requirer_model.integrate("app-b", "role-distributor")

        # Provider still blocked (no config set yet), but relation is wired
        provider_model.wait(
            lambda s: jubilant.all_blocked(s, "role-distributor"),
            timeout=SETTLE_TIMEOUT,
        )

    def test_machine_level_assignment(
        self,
        provider_model: jubilant.Juju,
        requirer_model: jubilant.Juju,
    ):
        """Set machine-level roles and verify all units receive assignments."""
        req_model_name = requirer_model.status().model.name
        app_a_machines = _get_machine_ids(requirer_model, "app-a")
        app_b_machines = _get_machine_ids(requirer_model, "app-b")

        applications: dict = {}
        _set_machine_defaults(applications, "app-a", app_a_machines, ["control"])
        _set_machine_defaults(applications, "app-b", app_b_machines, ["compute"])

        config = _build_config(req_model_name, applications)
        provider_model.config("role-distributor", {"role-mapping": config})

        expected_a = {name: "control" for name in app_a_machines}
        expected_b = {name: "compute" for name in app_b_machines}

        requirer_model.wait(
            lambda s: (
                _all_units_active_with_roles(s, "app-a", expected_a)
                and _all_units_active_with_roles(s, "app-b", expected_b)
            ),
            timeout=SETTLE_TIMEOUT,
        )
        provider_model.wait(jubilant.all_active, timeout=SETTLE_TIMEOUT)

    def test_unit_level_override(
        self,
        provider_model: jubilant.Juju,
        requirer_model: jubilant.Juju,
    ):
        """Override one unit's roles and verify others keep machine-level roles."""
        req_model_name = requirer_model.status().model.name
        app_a_machines = _get_machine_ids(requirer_model, "app-a")
        app_b_machines = _get_machine_ids(requirer_model, "app-b")

        applications: dict = {}
        _set_machine_defaults(applications, "app-a", app_a_machines, ["control"])
        _set_machine_defaults(applications, "app-b", app_b_machines, ["compute"])
        _set_unit_override(applications, "app-a", "app-a/0", ["storage"])

        config = _build_config(req_model_name, applications)
        provider_model.config("role-distributor", {"role-mapping": config})

        def check(status: jubilant.Status) -> bool:
            if not _unit_has_status(status, "app-a", "app-a/0", "active", "roles: storage"):
                return False
            for name in app_a_machines:
                if name == "app-a/0":
                    continue
                if not _unit_has_status(status, "app-a", name, "active", "roles: control"):
                    return False
            for name in app_b_machines:
                if not _unit_has_status(status, "app-b", name, "active", "roles: compute"):
                    return False
            return True

        requirer_model.wait(check, timeout=SETTLE_TIMEOUT)

    def test_workload_params_app_scoping(
        self,
        provider_model: jubilant.Juju,
        requirer_model: jubilant.Juju,
    ):
        """Verify app-scoped workload-params reach only the correct app."""
        req_model_name = requirer_model.status().model.name
        app_a_machines = _get_machine_ids(requirer_model, "app-a")
        app_b_machines = _get_machine_ids(requirer_model, "app-b")

        applications: dict = {}
        _set_machine_defaults(
            applications,
            "app-a",
            app_a_machines,
            ["control"],
            workload_params={"osd-count": 3},
        )
        _set_machine_defaults(
            applications,
            "app-b",
            app_b_machines,
            ["compute"],
            workload_params={"network-mode": "vlan"},
        )
        _set_unit_override(applications, "app-a", "app-a/0", ["storage"])

        config = _build_config(req_model_name, applications)
        provider_model.config("role-distributor", {"role-mapping": config})

        requirer_model.wait(
            lambda s: jubilant.all_active(s, "app-a", "app-b"),
            timeout=SETTLE_TIMEOUT,
        )

        task_a0 = requirer_model.run("app-a/0", "get-assignment", wait=60)
        assignment_a0 = json.loads(task_a0.results["assignment"])
        assert assignment_a0.get("workload-params") == {"osd-count": 3}

        task_b0 = requirer_model.run("app-b/0", "get-assignment", wait=60)
        assignment_b0 = json.loads(task_b0.results["assignment"])
        assert assignment_b0.get("workload-params") == {"network-mode": "vlan"}

    def test_unmatched_unit_pending(
        self,
        provider_model: jubilant.Juju,
        requirer_model: jubilant.Juju,
    ):
        """A new unit whose machine-id is not in config stays pending."""
        existing_units = set(_get_machine_ids(requirer_model, "app-b").keys())

        requirer_model.add_unit("app-b")

        def new_unit_appeared(status: jubilant.Status) -> bool:
            units = status.get_units("app-b")
            return len(units) > len(existing_units)

        requirer_model.wait(new_unit_appeared, timeout=DEPLOY_TIMEOUT)

        current_units = set(_get_machine_ids(requirer_model, "app-b").keys())
        new_unit = (current_units - existing_units).pop()

        requirer_model.wait(
            lambda s: _unit_has_status(s, "app-b", new_unit, "waiting"),
            timeout=SETTLE_TIMEOUT,
        )

        provider_model.wait(
            lambda _: (_get_assignment(requirer_model, new_unit) or {}).get("status") == "pending",
            timeout=DEPLOY_TIMEOUT,
        )

    def test_scale_up_assigns_new_unit(
        self,
        provider_model: jubilant.Juju,
        requirer_model: jubilant.Juju,
    ):
        """Adding the new unit's machine to config assigns it."""
        req_model_name = requirer_model.status().model.name
        app_a_machines = _get_machine_ids(requirer_model, "app-a")
        app_b_machines = _get_machine_ids(requirer_model, "app-b")

        applications: dict = {}
        _set_machine_defaults(
            applications,
            "app-a",
            app_a_machines,
            ["control"],
            workload_params={"osd-count": 3},
        )
        _set_machine_defaults(
            applications,
            "app-b",
            app_b_machines,
            ["compute"],
            workload_params={"network-mode": "vlan"},
        )
        _set_unit_override(applications, "app-a", "app-a/0", ["storage"])

        config = _build_config(req_model_name, applications)
        provider_model.config("role-distributor", {"role-mapping": config})

        requirer_model.wait(
            lambda s: jubilant.all_active(s, "app-a", "app-b"),
            timeout=DEPLOY_TIMEOUT,
        )
        provider_model.wait(jubilant.all_active, timeout=DEPLOY_TIMEOUT)

    def test_relation_removal(
        self,
        provider_model: jubilant.Juju,
        requirer_model: jubilant.Juju,
    ):
        """Removing app-b's relation revokes its assignments without affecting app-a."""
        requirer_model.remove_relation("app-b", "role-distributor")

        requirer_model.wait(
            lambda s: jubilant.all_waiting(s, "app-b"),
            timeout=SETTLE_TIMEOUT,
        )

        requirer_model.wait(
            lambda s: jubilant.all_active(s, "app-a"),
            timeout=SETTLE_TIMEOUT,
        )

        provider_model.wait(jubilant.all_active, timeout=SETTLE_TIMEOUT)

    def test_re_establish_relation(
        self,
        provider_model: jubilant.Juju,
        requirer_model: jubilant.Juju,
    ):
        """Re-integrating after removal restores assignments."""
        app_b_machines = _get_machine_ids(requirer_model, "app-b")

        requirer_model.integrate("app-b", "role-distributor")

        expected_b = {name: "compute" for name in app_b_machines}
        requirer_model.wait(
            lambda s: _all_units_active_with_roles(s, "app-b", expected_b),
            timeout=SETTLE_TIMEOUT,
        )

        requirer_model.wait(
            lambda s: jubilant.all_active(s, "app-a"),
            timeout=SETTLE_TIMEOUT,
        )
        provider_model.wait(jubilant.all_active, timeout=SETTLE_TIMEOUT)

    def test_suspend_resume_relation(
        self,
        provider_model: jubilant.Juju,
        requirer_model: jubilant.Juju,
    ):
        """Suspended relations block updates; resume restores data flow."""
        req_model_name = requirer_model.status().model.name
        app_a_machines = _get_machine_ids(requirer_model, "app-a")
        app_b_machines = _get_machine_ids(requirer_model, "app-b")

        relation_ids = _get_offer_relation_ids(provider_model)
        assert len(relation_ids) >= 2, f"Expected >=2 relations, got {relation_ids}"

        for rid in relation_ids:
            provider_model.cli("suspend-relation", str(rid))

        # Change config: give all machines "network" role
        applications: dict = {}
        _set_machine_defaults(applications, "app-a", app_a_machines, ["network"])
        _set_machine_defaults(applications, "app-b", app_b_machines, ["network"])

        config = _build_config(req_model_name, applications)
        provider_model.config("role-distributor", {"role-mapping": config})

        # Neither app should have "network" yet (all relations suspended)
        time.sleep(5)
        status = requirer_model.status()
        for name in list(app_a_machines) + list(app_b_machines):
            app = "app-a" if name.startswith("app-a") else "app-b"
            unit = status.get_units(app).get(name)
            assert unit is not None
            assert "network" not in unit.workload_status.message

        for rid in relation_ids:
            provider_model.cli("resume-relation", str(rid))

        expected_a = {name: "network" for name in app_a_machines}
        expected_b = {name: "network" for name in app_b_machines}
        requirer_model.wait(
            lambda s: (
                _all_units_active_with_roles(s, "app-a", expected_a)
                and _all_units_active_with_roles(s, "app-b", expected_b)
            ),
            timeout=SETTLE_TIMEOUT,
        )

    def test_provider_config_cleared_and_restored(
        self,
        provider_model: jubilant.Juju,
        requirer_model: jubilant.Juju,
    ):
        """Empty model config causes all units to become pending; restoring recovers."""
        req_model_name = requirer_model.status().model.name

        # Set config to model with no entries — all units become pending
        config = _build_config(req_model_name, {})
        provider_model.config("role-distributor", {"role-mapping": config})

        provider_model.wait(
            lambda s: jubilant.all_waiting(s, "role-distributor"),
            timeout=SETTLE_TIMEOUT,
        )

        requirer_model.wait(
            lambda s: jubilant.all_blocked(s, "app-a") and jubilant.all_blocked(s, "app-b"),
            timeout=SETTLE_TIMEOUT,
        )

        # Restore proper config
        app_a_machines = _get_machine_ids(requirer_model, "app-a")
        app_b_machines = _get_machine_ids(requirer_model, "app-b")
        applications: dict = {}
        _set_machine_defaults(applications, "app-a", app_a_machines, ["control"])
        _set_machine_defaults(applications, "app-b", app_b_machines, ["compute"])

        config = _build_config(req_model_name, applications)
        provider_model.config("role-distributor", {"role-mapping": config})

        expected_a = {name: "control" for name in app_a_machines}
        expected_b = {name: "compute" for name in app_b_machines}
        requirer_model.wait(
            lambda s: (
                _all_units_active_with_roles(s, "app-a", expected_a)
                and _all_units_active_with_roles(s, "app-b", expected_b)
            ),
            timeout=SETTLE_TIMEOUT,
        )
        provider_model.wait(jubilant.all_active, timeout=SETTLE_TIMEOUT)

    def test_remove_provider_application(
        self,
        charm: pathlib.Path,
        provider_model: jubilant.Juju,
        requirer_model: jubilant.Juju,
    ):
        """Removing and re-deploying the provider restores assignments end-to-end."""
        provider_name = provider_model.status().model.name
        req_model_name = requirer_model.status().model.name

        requirer_model.remove_relation("app-a", "role-distributor")
        requirer_model.remove_relation("app-b", "role-distributor")

        requirer_model.wait(
            lambda s: jubilant.all_waiting(s, "app-a") and jubilant.all_waiting(s, "app-b"),
            timeout=SETTLE_TIMEOUT,
        )

        offer_url = f"{provider_name}.role-distributor"
        with contextlib.suppress(jubilant.CLIError):
            provider_model.cli("remove-offer", offer_url, "--force")
        provider_model.wait(
            lambda _: not _offer_exists(provider_model, offer_url),
            timeout=SETTLE_TIMEOUT,
        )
        with contextlib.suppress(jubilant.CLIError):
            requirer_model.cli("remove-saas", "role-distributor")
        requirer_model.wait(
            lambda s: "role-distributor" not in s.apps,
            timeout=SETTLE_TIMEOUT,
        )

        provider_model.remove_application("role-distributor", force=True)
        provider_model.wait(
            lambda s: "role-distributor" not in s.apps,
            timeout=DEPLOY_TIMEOUT,
        )

        provider_model.deploy(f"./{charm}")
        provider_model.wait(
            lambda s: jubilant.all_blocked(s, "role-distributor"),
            timeout=DEPLOY_TIMEOUT,
        )

        provider_model.offer(
            offer_url,
            endpoint="role-assignment",
        )
        requirer_model.consume(offer_url)
        requirer_model.integrate("app-a", "role-distributor")
        requirer_model.integrate("app-b", "role-distributor")

        app_a_machines = _get_machine_ids(requirer_model, "app-a")
        app_b_machines = _get_machine_ids(requirer_model, "app-b")
        applications: dict = {}
        _set_machine_defaults(applications, "app-a", app_a_machines, ["control"])
        _set_machine_defaults(applications, "app-b", app_b_machines, ["compute"])

        config = _build_config(req_model_name, applications)
        provider_model.config("role-distributor", {"role-mapping": config})

        expected_a = {name: "control" for name in app_a_machines}
        expected_b = {name: "compute" for name in app_b_machines}
        requirer_model.wait(
            lambda s: (
                _all_units_active_with_roles(s, "app-a", expected_a)
                and _all_units_active_with_roles(s, "app-b", expected_b)
            ),
            timeout=SETTLE_TIMEOUT,
        )
        provider_model.wait(jubilant.all_active, timeout=SETTLE_TIMEOUT)
