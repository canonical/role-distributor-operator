"""Cross-model integration tests for role-distributor charm."""

from __future__ import annotations

import json
import pathlib

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
        # Discover machine IDs
        app_a_machines = _get_machine_ids(requirer_model, "app-a")
        app_b_machines = _get_machine_ids(requirer_model, "app-b")

        # Build config mapping each machine to roles
        machines_block = {}
        for _unit_name, mid in app_a_machines.items():
            machines_block[mid] = {"roles": ["control"]}
        for _unit_name, mid in app_b_machines.items():
            machines_block[mid] = {"roles": ["compute"]}

        config = yaml.dump({"machines": machines_block})
        provider_model.config("role-distributor", {"role-mapping": config})

        # Wait for all units to be active with roles
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
        app_a_machines = _get_machine_ids(requirer_model, "app-a")
        app_b_machines = _get_machine_ids(requirer_model, "app-b")

        # Build config: machines same as before, plus unit override for app-a/0
        machines_block = {}
        for _unit_name, mid in app_a_machines.items():
            machines_block[mid] = {"roles": ["control"]}
        for _unit_name, mid in app_b_machines.items():
            machines_block[mid] = {"roles": ["compute"]}

        config = yaml.dump(
            {
                "machines": machines_block,
                "units": {"app-a/0": {"roles": ["storage"]}},
            }
        )
        provider_model.config("role-distributor", {"role-mapping": config})

        # app-a/0 should get storage, app-a/1 keeps control, app-b keeps compute
        def check(status: jubilant.Status) -> bool:
            if not _unit_has_status(status, "app-a", "app-a/0", "active", "roles: storage"):
                return False
            # All other app-a units keep control
            for name in app_a_machines:
                if name == "app-a/0":
                    continue
                if not _unit_has_status(status, "app-a", name, "active", "roles: control"):
                    return False
            # app-b unchanged
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
        app_a_machines = _get_machine_ids(requirer_model, "app-a")
        app_b_machines = _get_machine_ids(requirer_model, "app-b")

        # Build config with app-scoped workload-params on machines
        machines_block = {}
        for _unit_name, mid in app_a_machines.items():
            machines_block[mid] = {
                "roles": ["control"],
                "workload-params": {
                    "app-a": {"osd-count": 3},
                    "app-b": {"network-mode": "flat"},
                },
            }
        for _unit_name, mid in app_b_machines.items():
            machines_block[mid] = {
                "roles": ["compute"],
                "workload-params": {
                    "app-b": {"network-mode": "vlan"},
                },
            }

        config = yaml.dump(
            {
                "machines": machines_block,
                "units": {"app-a/0": {"roles": ["storage"]}},
            }
        )
        provider_model.config("role-distributor", {"role-mapping": config})

        # Wait for settle
        requirer_model.wait(
            lambda s: jubilant.all_active(s, "app-a", "app-b"),
            timeout=SETTLE_TIMEOUT,
        )

        # Check app-a/0 — unit override with no unit-level workload-params,
        # so it gets machine-level params scoped to app-a
        task_a0 = requirer_model.run("app-a/0", "get-assignment", wait=60)
        assignment_a0 = json.loads(task_a0.results["assignment"])
        assert assignment_a0.get("workload-params") == {"osd-count": 3}

        # Check app-b/0 — should get app-b scoped params from its own machine
        task_b0 = requirer_model.run("app-b/0", "get-assignment", wait=60)
        assignment_b0 = json.loads(task_b0.results["assignment"])
        assert assignment_b0.get("workload-params") == {"network-mode": "vlan"}

    def test_unmatched_unit_pending(
        self,
        provider_model: jubilant.Juju,
        requirer_model: jubilant.Juju,
    ):
        """A new unit whose machine-id is not in config stays pending."""
        # Record existing units before scale-up
        existing_units = set(_get_machine_ids(requirer_model, "app-b").keys())

        # Scale up
        requirer_model.add_unit("app-b")

        # Wait for new unit to appear
        def new_unit_appeared(status: jubilant.Status) -> bool:
            units = status.get_units("app-b")
            return len(units) > len(existing_units)

        requirer_model.wait(new_unit_appeared, timeout=DEPLOY_TIMEOUT)

        # Identify the new unit
        current_units = set(_get_machine_ids(requirer_model, "app-b").keys())
        new_unit = (current_units - existing_units).pop()

        # New unit should be waiting (no assignment for its machine)
        requirer_model.wait(
            lambda s: _unit_has_status(s, "app-b", new_unit, "waiting"),
            timeout=SETTLE_TIMEOUT,
        )

        # Provider should report units awaiting assignment
        provider_model.wait(
            lambda s: jubilant.all_waiting(s, "role-distributor"),
            timeout=SETTLE_TIMEOUT,
        )

    def test_scale_up_assigns_new_unit(
        self,
        provider_model: jubilant.Juju,
        requirer_model: jubilant.Juju,
    ):
        """Adding the new unit's machine to config assigns it."""
        app_a_machines = _get_machine_ids(requirer_model, "app-a")
        app_b_machines = _get_machine_ids(requirer_model, "app-b")

        # Build config including ALL machine IDs (including the newly scaled unit)
        machines_block = {}
        for _unit_name, mid in app_a_machines.items():
            machines_block[mid] = {
                "roles": ["control"],
                "workload-params": {
                    "app-a": {"osd-count": 3},
                    "app-b": {"network-mode": "flat"},
                },
            }
        for _unit_name, mid in app_b_machines.items():
            machines_block[mid] = {
                "roles": ["compute"],
                "workload-params": {
                    "app-b": {"network-mode": "vlan"},
                },
            }

        config = yaml.dump(
            {
                "machines": machines_block,
                "units": {"app-a/0": {"roles": ["storage"]}},
            }
        )
        provider_model.config("role-distributor", {"role-mapping": config})

        # All units should now be active
        requirer_model.wait(
            lambda s: jubilant.all_active(s, "app-a", "app-b"),
            timeout=SETTLE_TIMEOUT,
        )
        provider_model.wait(jubilant.all_active, timeout=SETTLE_TIMEOUT)

    def test_relation_removal(
        self,
        provider_model: jubilant.Juju,
        requirer_model: jubilant.Juju,
    ):
        """Removing app-b's relation revokes its assignments without affecting app-a."""
        requirer_model.remove_relation("app-b", "role-distributor")

        # app-b units should revert to waiting
        requirer_model.wait(
            lambda s: jubilant.all_waiting(s, "app-b"),
            timeout=SETTLE_TIMEOUT,
        )

        # app-a should remain active
        requirer_model.wait(
            lambda s: jubilant.all_active(s, "app-a"),
            timeout=SETTLE_TIMEOUT,
        )

        # Provider should stay active (app-a still assigned)
        provider_model.wait(jubilant.all_active, timeout=SETTLE_TIMEOUT)
