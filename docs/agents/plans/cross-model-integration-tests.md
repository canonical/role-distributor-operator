# Cross-Model Integration Tests Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add end-to-end cross-model integration tests with a dummy requirer charm that validates the role-assignment protocol works through `juju offer`/`juju consume`.

**Architecture:** A dummy requirer charm lives at `tests/integration/charms/dummy-requirer/` and uses the `RoleAssignmentRequirer` lib to register, receive assignments, and expose them via a `get-assignment` action. A tox target copies the lib and packs the charm. Tests in `test_cross_model.py` deploy both charms across two Juju models and exercise seven scenarios.

**Tech Stack:** Python 3.12, ops, jubilant, pytest, charmcraft, tox

**Spec:** `docs/specs/2026-03-24-cross-model-integration-tests-design.md`

---

## File Structure

### Files to Create

| File | Responsibility |
|------|---------------|
| `tests/integration/charms/dummy-requirer/charmcraft.yaml` | Charm metadata, build config, action declaration |
| `tests/integration/charms/dummy-requirer/src/charm.py` | Requirer charm: registers with machine-id, validates assignments, exposes via action |
| `tests/integration/charms/dummy-requirer/requirements.txt` | Runtime dependency: `ops` |
| `tests/integration/charms/dummy-requirer/pyproject.toml` | Minimal project metadata for uv plugin |
| `tests/integration/test_cross_model.py` | Seven cross-model test scenarios in a single class |

### Files to Modify

| File | Change |
|------|--------|
| `tests/integration/conftest.py` | Add `provider_model`, `requirer_model`, `dummy_charm` fixtures |
| `tox.ini` | Add `build-dummy` target |

---

### Task 1: Create the dummy requirer charm metadata

**Files:**
- Create: `tests/integration/charms/dummy-requirer/charmcraft.yaml`
- Create: `tests/integration/charms/dummy-requirer/requirements.txt`
- Create: `tests/integration/charms/dummy-requirer/pyproject.toml`

- [ ] **Step 1: Create `charmcraft.yaml`**

```yaml
name: dummy-requirer
type: charm
summary: Test charm that consumes the role-assignment interface
description: |
  Minimal requirer charm for integration testing the role-distributor.
  Validates received assignments and exposes them via the get-assignment action.

base: ubuntu@24.04
platforms:
  amd64:

parts:
  dummy-requirer:
    plugin: uv
    source: .
    build-snaps:
      - astral-uv

requires:
  role-assignment:
    interface: role-assignment
    limit: 1

actions:
  get-assignment:
    description: Return the current role assignment as JSON.
```

- [ ] **Step 2: Create `requirements.txt`**

```
ops
```

- [ ] **Step 3: Create `pyproject.toml`**

```toml
[project]
name = "dummy-requirer"
version = "0.0.1"
requires-python = ">=3.12"

dependencies = [
    "ops",
]

[build-system]
requires = ["setuptools>=75"]
build-backend = "setuptools.build_meta"
```

- [ ] **Step 4: Commit**

```bash
git add tests/integration/charms/dummy-requirer/charmcraft.yaml \
        tests/integration/charms/dummy-requirer/requirements.txt \
        tests/integration/charms/dummy-requirer/pyproject.toml
git commit -m "chore: add dummy-requirer charm metadata for integration tests"
```

---

### Task 2: Implement the dummy requirer charm

**Files:**
- Create: `tests/integration/charms/dummy-requirer/src/charm.py`

**Context:** The charm must:
1. Use `RoleAssignmentRequirer` from the lib (will be copied at build time).
2. Write `machine-id` to the relation databag on `relation-joined` (the lib does NOT do this).
3. Validate assignments and reflect them in status messages.
4. Expose the full assignment via the `get-assignment` action.

- [ ] **Step 1: Create `src/charm.py`**

```python
#!/usr/bin/env python3
"""Dummy requirer charm for integration testing role-assignment."""

from __future__ import annotations

import json
import os

import ops
from charms.role_distributor.v0.role_assignment import RoleAssignmentRequirer


class DummyRequirerCharm(ops.CharmBase):
    """Minimal charm that consumes role-assignment and validates assignments."""

    def __init__(self, framework: ops.Framework):
        super().__init__(framework)
        self._requirer = RoleAssignmentRequirer(self, "role-assignment")
        framework.observe(
            self._requirer.on.role_assignment_changed,
            self._on_role_assignment_changed,
        )
        framework.observe(
            self._requirer.on.role_assignment_revoked,
            self._on_role_assignment_revoked,
        )
        framework.observe(
            self.on["role-assignment"].relation_joined,
            self._on_relation_joined,
        )
        framework.observe(self.on.get_assignment_action, self._on_get_assignment)

    def _on_relation_joined(self, event: ops.RelationJoinedEvent) -> None:
        machine_id = os.environ.get("JUJU_MACHINE_ID")
        if machine_id is not None:
            event.relation.data[self.unit]["machine-id"] = machine_id

    def _on_role_assignment_changed(self, event: ops.EventBase) -> None:
        assignment = self._requirer.get_assignment()
        if assignment is None:
            return
        if assignment.status != "assigned":
            self.unit.status = ops.BlockedStatus(
                f"invalid assignment: status={assignment.status}"
            )
            return
        if not assignment.roles:
            self.unit.status = ops.BlockedStatus("invalid assignment: empty roles")
            return
        self.unit.status = ops.ActiveStatus(
            f"roles: {','.join(assignment.roles)}"
        )

    def _on_role_assignment_revoked(self, _event: ops.EventBase) -> None:
        self.unit.status = ops.WaitingStatus("no assignment")

    def _on_get_assignment(self, event: ops.ActionEvent) -> None:
        assignment = self._requirer.get_assignment()
        if assignment is None:
            event.set_results({"assignment": json.dumps(None)})
            return
        event.set_results({"assignment": json.dumps(assignment.to_dict())})


if __name__ == "__main__":
    ops.main(DummyRequirerCharm)
```

- [ ] **Step 2: Commit**

```bash
git add tests/integration/charms/dummy-requirer/src/charm.py
git commit -m "feat: implement dummy-requirer charm for cross-model integration tests"
```

---

### Task 3: Add the `build-dummy` tox target

**Files:**
- Modify: `tox.ini`

**Context:** The target must copy the lib (including `__init__.py` files for the package hierarchy) into the dummy charm, then run `charmcraft pack`. The copied lib directory should be in `.gitignore` to avoid committing generated files.

- [ ] **Step 1: Create `.gitignore` for the dummy charm's lib directory**

Create `tests/integration/charms/dummy-requirer/.gitignore`:

```
lib/
*.charm
```

- [ ] **Step 2: Add `build-dummy` target to `tox.ini`**

Append after the `[testenv:integration]` block:

```ini
[testenv:build-dummy]
description = build the dummy-requirer test charm
skip_install = true
allowlist_externals =
    mkdir
    cp
    charmcraft
commands =
    mkdir -p {tox_root}/tests/integration/charms/dummy-requirer/lib/charms/role_distributor/v0
    cp {tox_root}/lib/charms/__init__.py {tox_root}/tests/integration/charms/dummy-requirer/lib/charms/__init__.py
    cp {tox_root}/lib/charms/role_distributor/__init__.py {tox_root}/tests/integration/charms/dummy-requirer/lib/charms/role_distributor/__init__.py
    cp {tox_root}/lib/charms/role_distributor/v0/__init__.py {tox_root}/tests/integration/charms/dummy-requirer/lib/charms/role_distributor/v0/__init__.py
    cp {tox_root}/lib/charms/role_distributor/v0/role_assignment.py {tox_root}/tests/integration/charms/dummy-requirer/lib/charms/role_distributor/v0/role_assignment.py
    charmcraft pack -p {tox_root}/tests/integration/charms/dummy-requirer
```

- [ ] **Step 3: Verify the `__init__.py` files exist in the lib tree**

Run: `ls lib/charms/__init__.py lib/charms/role_distributor/__init__.py lib/charms/role_distributor/v0/__init__.py`

If any are missing, create empty `__init__.py` files as needed.

- [ ] **Step 4: Commit**

```bash
git add tox.ini tests/integration/charms/dummy-requirer/.gitignore
git commit -m "chore: add build-dummy tox target for dummy-requirer charm"
```

---

### Task 4: Add cross-model fixtures to conftest.py

**Files:**
- Modify: `tests/integration/conftest.py`

**Context:** The existing `juju` and `charm` fixtures remain unchanged (used by `test_charm.py`). New fixtures are added for `test_cross_model.py`. Key jubilant API details:
- `jubilant.temp_model()` → context manager yielding `Juju` instance
- `juju.status().model.name` → the model name string
- `juju.offer(f"{model_name}.app", endpoint="role-assignment")` — `offer` uses `include_model=False` so model must be in the app argument
- `juju.consume(f"{model_name}.app")` — consume uses `include_model=True` by default
- UnitStatus has `.machine` (string), `.workload_status.current`, `.workload_status.message`

- [ ] **Step 1: Add `dummy_charm` fixture**

Add to `conftest.py` after the existing `charm` fixture:

```python
@pytest.fixture(scope="session")
def dummy_charm():
    """Return the path of the dummy-requirer .charm file."""
    if "DUMMY_CHARM_PATH" in os.environ:
        charm_path = pathlib.Path(os.environ["DUMMY_CHARM_PATH"])
        if not charm_path.exists():
            raise FileNotFoundError(f"Dummy charm does not exist: {charm_path}")
        return charm_path
    return next(pathlib.Path("tests/integration/charms/dummy-requirer").glob("*.charm"))
```

- [ ] **Step 2: Add `provider_model` and `requirer_model` fixtures**

Add to `conftest.py`:

```python
@pytest.fixture(scope="module")
def provider_model(request: pytest.FixtureRequest):
    """Create a temporary Juju model for the role-distributor (provider)."""
    with jubilant.temp_model() as juju:
        yield juju
        if request.session.testsfailed:
            logger.info("Collecting provider model Juju logs...")
            time.sleep(0.5)
            log = juju.debug_log(limit=1000)
            print(log, end="", file=sys.stderr)


@pytest.fixture(scope="module")
def requirer_model(request: pytest.FixtureRequest):
    """Create a temporary Juju model for the dummy-requirer apps."""
    with jubilant.temp_model() as juju:
        yield juju
        if request.session.testsfailed:
            logger.info("Collecting requirer model Juju logs...")
            time.sleep(0.5)
            log = juju.debug_log(limit=1000)
            print(log, end="", file=sys.stderr)
```

- [ ] **Step 3: Commit**

```bash
git add tests/integration/conftest.py
git commit -m "feat: add cross-model fixtures and dummy_charm fixture to conftest"
```

---

### Task 5: Write test_cross_model.py — deploy and relate (scenario 1)

**Files:**
- Create: `tests/integration/test_cross_model.py`

**Context:** All seven tests go in a single class `TestCrossModel` for ordered execution. This task writes the class skeleton, constants, and the first test. Key jubilant patterns:
- `juju.deploy(f"./{charm}", app="app-a", num_units=2)` — deploys with custom app name
- `juju.wait(predicate, timeout=N)` — waits with timeout
- `juju.offer(f"{model_name}.role-distributor", endpoint="role-assignment")`
- `juju.consume(f"{model_name}.role-distributor")`
- `juju.integrate("app-a", "role-distributor")`

- [ ] **Step 1: Create the test file with class skeleton and scenario 1**

```python
"""Cross-model integration tests for role-distributor charm."""

from __future__ import annotations

import json
import pathlib

import jubilant
import yaml

DEPLOY_TIMEOUT = 15 * 60.0  # 15 minutes for machine charm deploys
SETTLE_TIMEOUT = 5 * 60.0   # 5 minutes for config/relation changes to settle


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
    if expected_message is not None and unit.workload_status.message != expected_message:
        return False
    return True


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
            lambda s: (
                jubilant.all_waiting(s, "app-a")
                and jubilant.all_waiting(s, "app-b")
            ),
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
```

- [ ] **Step 2: Run linting to verify**

Run: `tox -e lint -- tests/integration/test_cross_model.py`

- [ ] **Step 3: Commit**

```bash
git add tests/integration/test_cross_model.py
git commit -m "feat: add cross-model test scaffold with deploy and relate scenario"
```

---

### Task 6: Write scenario 2 — machine-level assignment

**Files:**
- Modify: `tests/integration/test_cross_model.py`

- [ ] **Step 1: Add `test_machine_level_assignment`**

Add to `TestCrossModel` class after the first test:

```python
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
        for unit_name, mid in app_a_machines.items():
            machines_block[mid] = {"roles": ["control"]}
        for unit_name, mid in app_b_machines.items():
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
```

- [ ] **Step 2: Commit**

```bash
git add tests/integration/test_cross_model.py
git commit -m "feat: add machine-level assignment cross-model test"
```

---

### Task 7: Write scenario 3 — unit-level override

**Files:**
- Modify: `tests/integration/test_cross_model.py`

- [ ] **Step 1: Add `test_unit_level_override`**

Add to `TestCrossModel` class:

```python
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
        for unit_name, mid in app_a_machines.items():
            machines_block[mid] = {"roles": ["control"]}
        for unit_name, mid in app_b_machines.items():
            machines_block[mid] = {"roles": ["compute"]}

        config = yaml.dump({
            "machines": machines_block,
            "units": {"app-a/0": {"roles": ["storage"]}},
        })
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
```

- [ ] **Step 2: Commit**

```bash
git add tests/integration/test_cross_model.py
git commit -m "feat: add unit-level override cross-model test"
```

---

### Task 8: Write scenario 4 — workload-params app scoping

**Files:**
- Modify: `tests/integration/test_cross_model.py`

**Context:** This test uses `juju.run(unit, action)` to invoke the `get-assignment` action. `juju.run()` returns a `Task` with `.results` dict. The action sets `assignment` key to a JSON string.

- [ ] **Step 1: Add `test_workload_params_app_scoping`**

Add to `TestCrossModel` class:

```python
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
        for unit_name, mid in app_a_machines.items():
            machines_block[mid] = {
                "roles": ["control"],
                "workload-params": {
                    "app-a": {"osd-count": 3},
                    "app-b": {"network-mode": "flat"},
                },
            }
        for unit_name, mid in app_b_machines.items():
            machines_block[mid] = {
                "roles": ["compute"],
                "workload-params": {
                    "app-b": {"network-mode": "vlan"},
                },
            }

        config = yaml.dump({
            "machines": machines_block,
            "units": {"app-a/0": {"roles": ["storage"]}},
        })
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
```

- [ ] **Step 2: Commit**

```bash
git add tests/integration/test_cross_model.py
git commit -m "feat: add workload-params app scoping cross-model test"
```

---

### Task 9: Write scenario 5 — unmatched unit pending

**Files:**
- Modify: `tests/integration/test_cross_model.py`

**Context:** `juju.add_unit("app-b")` scales up. The new unit's machine-id won't be in the config, so it should stay `WaitingStatus`.

- [ ] **Step 1: Add `test_unmatched_unit_pending`**

Add to `TestCrossModel` class:

```python
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
```

- [ ] **Step 2: Commit**

```bash
git add tests/integration/test_cross_model.py
git commit -m "feat: add unmatched unit pending cross-model test"
```

---

### Task 10: Write scenario 6 — scale up assigns new unit

**Files:**
- Modify: `tests/integration/test_cross_model.py`

- [ ] **Step 1: Add `test_scale_up_assigns_new_unit`**

Add to `TestCrossModel` class:

```python
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
        for unit_name, mid in app_a_machines.items():
            machines_block[mid] = {
                "roles": ["control"],
                "workload-params": {
                    "app-a": {"osd-count": 3},
                    "app-b": {"network-mode": "flat"},
                },
            }
        for unit_name, mid in app_b_machines.items():
            machines_block[mid] = {
                "roles": ["compute"],
                "workload-params": {
                    "app-b": {"network-mode": "vlan"},
                },
            }

        config = yaml.dump({
            "machines": machines_block,
            "units": {"app-a/0": {"roles": ["storage"]}},
        })
        provider_model.config("role-distributor", {"role-mapping": config})

        # All units should now be active
        requirer_model.wait(
            lambda s: jubilant.all_active(s, "app-a", "app-b"),
            timeout=SETTLE_TIMEOUT,
        )
        provider_model.wait(jubilant.all_active, timeout=SETTLE_TIMEOUT)
```

- [ ] **Step 2: Commit**

```bash
git add tests/integration/test_cross_model.py
git commit -m "feat: add scale-up assignment cross-model test"
```

---

### Task 11: Write scenario 7 — relation removal

**Files:**
- Modify: `tests/integration/test_cross_model.py`

**Context:** `juju.remove_relation("app-b", "role-distributor")` removes the cross-model relation from the requirer side. After removal, app-b units should get `WaitingStatus("no assignment")` via the revoked event, and the provider should stay active (app-a still assigned).

- [ ] **Step 1: Add `test_relation_removal`**

Add to `TestCrossModel` class:

```python
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
```

- [ ] **Step 2: Commit**

```bash
git add tests/integration/test_cross_model.py
git commit -m "feat: add relation removal cross-model test"
```

---

### Task 12: Lint and final review

**Files:**
- All created/modified files

- [ ] **Step 1: Run linting on all test files**

Run: `tox -e lint`

Fix any issues reported by ruff or ty.

- [ ] **Step 2: Verify the dummy charm directory structure**

Run: `find tests/integration/charms/dummy-requirer -type f | sort`

Expected:
```
tests/integration/charms/dummy-requirer/.gitignore
tests/integration/charms/dummy-requirer/charmcraft.yaml
tests/integration/charms/dummy-requirer/pyproject.toml
tests/integration/charms/dummy-requirer/requirements.txt
tests/integration/charms/dummy-requirer/src/charm.py
```

- [ ] **Step 3: Verify the complete test file parses**

Run: `python -c "import ast; ast.parse(open('tests/integration/test_cross_model.py').read()); print('OK')"`

- [ ] **Step 4: Final commit if any lint fixes were needed**

```bash
git add -u
git commit -m "chore: fix lint issues in cross-model integration tests"
```
