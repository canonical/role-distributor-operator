# Machine-ID & Workload-Params Library Update — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Update the `role_assignment.py` library and its tests to support `machine-id`, `application-name`, and `workload-params` as defined in the updated spec.

**Architecture:** The changes are additive — new optional fields on existing data classes, new parameters on existing events, and updated databag read/write logic. No new files are needed. The library remains stateless and the public API is backward-compatible (new parameters have defaults).

**Tech Stack:** Python, ops framework, ops.testing (Scenario)

**Spec:** `docs/specs/2026-03-18-role-assignment-interface-design.md`

**Note on line numbers:** Line references are based on the library as it exists before any task is applied. After each task, subsequent line numbers will shift. Treat all line references as approximate — locate code by content, not line number.

---

## File Map

| File | Action | Responsibility |
|------|--------|----------------|
| `lib/charms/role_distributor/v0/role_assignment.py` | Modify | Add `workload_params` to `UnitRoleAssignment`, `application_name`/`machine_id` to `RegisteredUnit`, update events, update Requirer/Provider read/write logic |
| `tests/unit/test_data_classes.py` | Modify | Add tests for new fields on both data classes |
| `tests/unit/test_provider.py` | Modify | Add tests for `application_name`/`machine_id` in registrations and events |
| `tests/unit/test_requirer.py` | Modify | Add tests for `application-name`/`machine-id` in databags, `workload_params` in events |

---

### Task 1: Add `workload_params` to `UnitRoleAssignment`

**Files:**
- Test: `tests/unit/test_data_classes.py`
- Modify: `lib/charms/role_distributor/v0/role_assignment.py:31-72`

- [ ] **Step 1: Write failing tests for `workload_params` on `UnitRoleAssignment`**

Add these tests to `TestUnitRoleAssignment` in `tests/unit/test_data_classes.py`:

```python
def test_assigned_with_workload_params(self):
    a = UnitRoleAssignment(
        status="assigned",
        roles=("control", "gateway"),
        workload_params={"flavors": ["rgw"]},
    )
    assert a.status == "assigned"
    assert a.roles == ("control", "gateway")
    assert a.workload_params == {"flavors": ["rgw"]}

def test_workload_params_defaults_to_none(self):
    a = UnitRoleAssignment(status="assigned", roles=("control",))
    assert a.workload_params is None

def test_to_dict_assigned_with_workload_params(self):
    a = UnitRoleAssignment(
        status="assigned",
        roles=("gateway",),
        workload_params={"flavors": ["rgw"]},
    )
    d = a.to_dict()
    assert d == {
        "status": "assigned",
        "roles": ["gateway"],
        "workload-params": {"flavors": ["rgw"]},
    }

def test_to_dict_assigned_without_workload_params(self):
    a = UnitRoleAssignment(status="assigned", roles=("control",))
    d = a.to_dict()
    assert "workload-params" not in d

def test_to_dict_pending_no_workload_params(self):
    """workload-params is only serialized for assigned status."""
    a = UnitRoleAssignment(status="pending", workload_params={"key": "val"})
    d = a.to_dict()
    assert "workload-params" not in d

def test_from_dict_with_workload_params(self):
    a = UnitRoleAssignment.from_dict(
        {
            "status": "assigned",
            "roles": ["gateway"],
            "workload-params": {"flavors": ["rgw"]},
        }
    )
    assert a.status == "assigned"
    assert a.roles == ("gateway",)
    assert a.workload_params == {"flavors": ["rgw"]}

def test_from_dict_without_workload_params(self):
    a = UnitRoleAssignment.from_dict(
        {"status": "assigned", "roles": ["storage"]}
    )
    assert a.workload_params is None

def test_from_dict_strips_workload_params_for_non_assigned(self):
    """workload-params is ignored when status is not assigned."""
    a = UnitRoleAssignment.from_dict(
        {"status": "pending", "workload-params": {"key": "val"}}
    )
    assert a.workload_params is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `tox -e unit -- tests/unit/test_data_classes.py -v`
Expected: FAIL — `UnitRoleAssignment` does not accept `workload_params`

- [ ] **Step 3: Implement `workload_params` on `UnitRoleAssignment`**

In `lib/charms/role_distributor/v0/role_assignment.py`, add the `typing.Any` import and modify `UnitRoleAssignment`:

Add to imports (line 22):
```python
from typing import Any, Literal
```

Add field after `message` (line 37):
```python
    workload_params: dict[str, Any] | None = None
```

Update `to_dict()` — add after the `roles` block (after line 49):
```python
        if self.workload_params is not None and self.status == "assigned":
            d["workload-params"] = self.workload_params
```

Update `from_dict()` — change the return statement (lines 68-72) to:
```python
        workload_params = (
            d.get("workload-params") if status == "assigned" else None
        )
        return cls(
            status=status,
            roles=roles,
            message=d.get("message"),
            workload_params=workload_params,
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `tox -e unit -- tests/unit/test_data_classes.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add lib/charms/role_distributor/v0/role_assignment.py tests/unit/test_data_classes.py
git commit -m "feat(library): add workload_params field to UnitRoleAssignment"
```

---

### Task 2: Add `application_name` and `machine_id` to `RegisteredUnit`

**Files:**
- Test: `tests/unit/test_data_classes.py`
- Modify: `lib/charms/role_distributor/v0/role_assignment.py:75-81`

- [ ] **Step 1: Write failing tests for new `RegisteredUnit` fields**

Add these tests to `TestRegisteredUnit` in `tests/unit/test_data_classes.py`:

```python
def test_creation_with_all_fields(self):
    u = RegisteredUnit(
        unit_name="microceph/0",
        model_name="ceph-model",
        application_name="microceph",
        machine_id="0",
    )
    assert u.unit_name == "microceph/0"
    assert u.model_name == "ceph-model"
    assert u.application_name == "microceph"
    assert u.machine_id == "0"

def test_machine_id_defaults_to_none(self):
    u = RegisteredUnit(
        unit_name="microceph/0",
        model_name="ceph-model",
        application_name="microceph",
    )
    assert u.machine_id is None
```

**Replace** the existing `test_creation` (it constructs `RegisteredUnit` without the new required `application_name` field):
```python
def test_creation(self):
    u = RegisteredUnit(
        unit_name="microceph/0",
        model_name="ceph-model",
        application_name="microceph",
    )
    assert u.unit_name == "microceph/0"
    assert u.model_name == "ceph-model"
    assert u.application_name == "microceph"
```

**Replace** the existing `test_frozen` similarly:
```python
def test_frozen(self):
    u = RegisteredUnit(
        unit_name="microceph/0",
        model_name="ceph-model",
        application_name="microceph",
    )
    with pytest.raises(AttributeError):
        u.unit_name = "other/1"  # type: ignore[misc]
```

**Also update `tests/unit/test_provider.py` in the same step** (these tests construct or assert on `RegisteredUnit` and will break once the field is added):

Update `test_get_registered_units_reads_remote_databags` in `TestProviderGetRegisteredUnits`:

```python
    def test_get_registered_units_reads_remote_databags(self):
        """Reads unit-name and machine-id from remote unit databags, model-name and application-name from app databag."""
        ctx = ops.testing.Context(
            ProviderCharmWithGetCapture, meta=ProviderCharmWithGetCapture.META
        )
        relation = ops.testing.Relation(
            endpoint="role-assignment",
            interface="role-assignment",
            remote_app_data={
                "model-name": "ceph-model",
                "application-name": "microceph",
            },
            remote_units_data={
                0: {"unit-name": "microceph/0", "machine-id": "0"},
                1: {"unit-name": "microceph/1"},
            },
        )
        state = ops.testing.State(relations=[relation], leader=True)
        ctx.run(ctx.on.relation_changed(relation), state)
        assert len(_registered_units_results) == 1
        units = _registered_units_results[0]
        assert len(units) == 2
        names = {u.unit_name for u in units}
        assert names == {"microceph/0", "microceph/1"}
        assert all(u.model_name == "ceph-model" for u in units)
        assert all(u.application_name == "microceph" for u in units)
        # Only unit 0 has machine-id
        by_name = {u.unit_name: u for u in units}
        assert by_name["microceph/0"].machine_id == "0"
        assert by_name["microceph/1"].machine_id is None
```

Update `test_get_registered_units_skips_units_without_name` in `TestProviderEdgeCases`:

```python
    def test_get_registered_units_skips_units_without_name(self):
        """Units that haven't written unit-name yet are skipped."""
        ctx = ops.testing.Context(
            ProviderCharmWithGetCapture, meta=ProviderCharmWithGetCapture.META
        )
        relation = ops.testing.Relation(
            endpoint="role-assignment",
            interface="role-assignment",
            remote_app_data={
                "model-name": "ceph-model",
                "application-name": "microceph",
            },
            remote_units_data={
                0: {"unit-name": "microceph/0"},
                1: {},
            },
        )
        state = ops.testing.State(relations=[relation], leader=True)
        ctx.run(ctx.on.relation_changed(relation), state)
        assert len(_registered_units_results) == 1
        units = _registered_units_results[0]
        assert len(units) == 1
        assert units[0].unit_name == "microceph/0"
        assert units[0].application_name == "microceph"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `tox -e unit -- tests/unit/test_data_classes.py::TestRegisteredUnit -v`
Expected: FAIL — `RegisteredUnit` does not accept `application_name` or `machine_id`

- [ ] **Step 3: Implement new fields on `RegisteredUnit`**

In `lib/charms/role_distributor/v0/role_assignment.py`, update `RegisteredUnit` (lines 75-80):

```python
@dataclasses.dataclass(frozen=True)
class RegisteredUnit:
    """A Requirer unit's registration as read from the relation databags."""

    unit_name: str
    model_name: str
    application_name: str
    machine_id: str | None = None
```

- [ ] **Step 4: Fix all `RegisteredUnit` construction sites in the library**

In `get_registered_units()` (lines 376-378), update to read `application-name` and `machine-id`:

```python
    def get_registered_units(
        self, relation: ops.Relation
    ) -> list[RegisteredUnit]:
        """Read all Requirer unit registrations from a single relation."""
        model_name = self._read_model_name(relation) or ""
        application_name = self._read_application_name(relation) or ""
        result = []
        for unit in relation.units:
            unit_name = relation.data[unit].get("unit-name")
            if not unit_name:
                continue
            machine_id = relation.data[unit].get("machine-id")
            result.append(
                RegisteredUnit(
                    unit_name=unit_name,
                    model_name=model_name,
                    application_name=application_name,
                    machine_id=machine_id,
                )
            )
        return result
```

This replaces the old `get_registered_units` which used `_read_unit_names()`. The `_read_unit_names()` helper is still used by event emission in `_on_relation_changed` and `_on_leader_elected` until Task 3 refactors those methods. It will be removed in Task 3.

Add the `_read_application_name` helper after `_read_model_name` (after line 361):

```python
    def _read_application_name(self, relation: ops.Relation) -> str | None:
        remote_app = relation.app
        if remote_app is None:
            return None
        return relation.data[remote_app].get("application-name")
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `tox -e unit -- tests/unit/test_data_classes.py tests/unit/test_provider.py -v`
Expected: ALL PASS

- [ ] **Step 6: Commit**

```bash
git add lib/charms/role_distributor/v0/role_assignment.py tests/unit/test_data_classes.py tests/unit/test_provider.py
git commit -m "feat(library): add application_name and machine_id to RegisteredUnit"
```

---

### Task 3: Update Provider events to carry `application_name` and `machine_id`

**Files:**
- Test: `tests/unit/test_provider.py`
- Modify: `lib/charms/role_distributor/v0/role_assignment.py:83-137` (event classes), `331-355` (event emission)

- [ ] **Step 1: Write failing tests for updated Provider events**

Update `ProviderCharm._on_registered` and `_on_departed` to capture the new fields, and add tests:

In `tests/unit/test_provider.py`, update the `ProviderCharm` handlers:

```python
    def _on_registered(self, event: RoleAssignmentUnitRegisteredEvent):
        _events_received.append(
            (
                "registered",
                event.unit_name,
                event.model_name,
                event.application_name,
                event.machine_id,
            )
        )

    def _on_departed(self, event: RoleAssignmentUnitDepartedEvent):
        _events_received.append(
            (
                "departed",
                event.unit_name,
                event.model_name,
                event.application_name,
                event.machine_id,
            )
        )
```

Update the existing `test_unit_registered_event_on_new_unit` to include new fields:

```python
    def test_unit_registered_event_on_new_unit(self):
        """unit_registered fires with all registration fields."""
        ctx = ops.testing.Context(ProviderCharm, meta=ProviderCharm.META)
        relation = ops.testing.Relation(
            endpoint="role-assignment",
            interface="role-assignment",
            remote_app_data={
                "model-name": "ceph-model",
                "application-name": "microceph",
            },
            remote_units_data={
                0: {"unit-name": "microceph/0", "machine-id": "3"},
            },
        )
        state = ops.testing.State(relations=[relation], leader=True)
        ctx.run(ctx.on.relation_changed(relation), state)
        assert (
            "registered", "microceph/0", "ceph-model", "microceph", "3"
        ) in _events_received
```

Add a test for unit without machine-id:

```python
    def test_unit_registered_event_without_machine_id(self):
        """unit_registered fires with machine_id=None when not provided."""
        ctx = ops.testing.Context(ProviderCharm, meta=ProviderCharm.META)
        relation = ops.testing.Relation(
            endpoint="role-assignment",
            interface="role-assignment",
            remote_app_data={
                "model-name": "ceph-model",
                "application-name": "microceph",
            },
            remote_units_data={
                0: {"unit-name": "microceph/0"},
            },
        )
        state = ops.testing.State(relations=[relation], leader=True)
        ctx.run(ctx.on.relation_changed(relation), state)
        assert (
            "registered", "microceph/0", "ceph-model", "microceph", None
        ) in _events_received
```

Add a test for `leader_elected` re-emission with new fields:

```python
    def test_leader_elected_re_emits_with_new_fields(self):
        """leader_elected re-emits unit_registered with application_name and machine_id."""
        ctx = ops.testing.Context(ProviderCharm, meta=ProviderCharm.META)
        relation = ops.testing.Relation(
            endpoint="role-assignment",
            interface="role-assignment",
            remote_app_data={
                "model-name": "ceph-model",
                "application-name": "microceph",
            },
            remote_units_data={
                0: {"unit-name": "microceph/0", "machine-id": "2"},
            },
        )
        state = ops.testing.State(relations=[relation], leader=True)
        ctx.run(ctx.on.leader_elected(), state)
        assert (
            "registered", "microceph/0", "ceph-model", "microceph", "2"
        ) in _events_received
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `tox -e unit -- tests/unit/test_provider.py::TestProviderEvents -v`
Expected: FAIL — events don't have `application_name` or `machine_id`

- [ ] **Step 3: Update `RoleAssignmentUnitRegisteredEvent`**

In `lib/charms/role_distributor/v0/role_assignment.py`, update `RoleAssignmentUnitRegisteredEvent` (lines 83-109):

```python
class RoleAssignmentUnitRegisteredEvent(ops.RelationEvent):
    """Emitted on the Provider when a new Requirer unit registers."""

    def __init__(
        self,
        handle,
        relation,
        unit_name: str,
        model_name: str,
        application_name: str,
        machine_id: str | None,
    ):
        super().__init__(handle, relation)
        self._unit_name = unit_name
        self._model_name = model_name
        self._application_name = application_name
        self._machine_id = machine_id

    @property
    def unit_name(self) -> str:
        return self._unit_name

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def application_name(self) -> str:
        return self._application_name

    @property
    def machine_id(self) -> str | None:
        return self._machine_id

    def snapshot(self) -> dict:
        d = super().snapshot()
        d["unit_name"] = self._unit_name
        d["model_name"] = self._model_name
        d["application_name"] = self._application_name
        d["machine_id"] = self._machine_id
        return d

    def restore(self, snapshot: dict) -> None:
        super().restore(snapshot)
        self._unit_name = snapshot["unit_name"]
        self._model_name = snapshot["model_name"]
        self._application_name = snapshot["application_name"]
        self._machine_id = snapshot["machine_id"]
```

- [ ] **Step 4: Update `RoleAssignmentUnitDepartedEvent`**

Same changes as Step 3 but for `RoleAssignmentUnitDepartedEvent` (lines 111-137). The signature and snapshot/restore are identical.

- [ ] **Step 5: Update Provider event emission to pass new fields**

Update `_on_relation_changed` (lines 331-338):

```python
    def _on_relation_changed(self, event: ops.RelationChangedEvent) -> None:
        model_name = self._read_model_name(event.relation) or ""
        application_name = self._read_application_name(event.relation) or ""
        for unit in event.relation.units:
            unit_name = event.relation.data[unit].get("unit-name")
            if not unit_name:
                continue
            machine_id = event.relation.data[unit].get("machine-id")
            self.on.unit_registered.emit(
                event.relation,
                unit_name,
                model_name,
                application_name,
                machine_id,
            )
```

Update `_on_relation_departed` (lines 340-348):

```python
    def _on_relation_departed(self, event: ops.RelationDepartedEvent) -> None:
        departing = event.departing_unit
        if departing is None:
            return
        unit_name = event.relation.data[departing].get("unit-name")
        if unit_name is None:
            return
        model_name = self._read_model_name(event.relation) or ""
        application_name = self._read_application_name(event.relation) or ""
        machine_id = event.relation.data[departing].get("machine-id")
        self.on.unit_departed.emit(
            event.relation, unit_name, model_name, application_name, machine_id
        )
```

Update `_on_leader_elected` (lines 350-355):

```python
    def _on_leader_elected(self, event: ops.LeaderElectedEvent) -> None:
        """Re-emit unit_registered for all units on all relations."""
        for rel in self._charm.model.relations.get(self._relation_name, []):
            model_name = self._read_model_name(rel) or ""
            application_name = self._read_application_name(rel) or ""
            for unit in rel.units:
                unit_name = rel.data[unit].get("unit-name")
                if not unit_name:
                    continue
                machine_id = rel.data[unit].get("machine-id")
                self.on.unit_registered.emit(
                    rel, unit_name, model_name, application_name, machine_id
                )
```

- [ ] **Step 6: Remove dead `_read_unit_names()` method**

After the refactoring in Step 5, `_read_unit_names()` has zero callers. Delete the entire method from `RoleAssignmentProvider`:

```python
    # DELETE this method — no longer used
    def _read_unit_names(self, relation: ops.Relation) -> list[str]:
        ...
```

Verify no references remain: `grep -n "_read_unit_names" lib/charms/role_distributor/v0/role_assignment.py`
Expected: no output

- [ ] **Step 7: Run tests to verify they pass**

Run: `tox -e unit -- tests/unit/test_provider.py -v`
Expected: ALL PASS

- [ ] **Step 8: Commit**

```bash
git add lib/charms/role_distributor/v0/role_assignment.py tests/unit/test_provider.py
git commit -m "feat(library): add application_name and machine_id to Provider events"
```

---

### Task 4: Update Requirer to write `application-name` and `machine-id`

**Files:**
- Test: `tests/unit/test_requirer.py`
- Modify: `lib/charms/role_distributor/v0/role_assignment.py:237-244` (Requirer `_on_relation_joined`), `260-263` (`_on_leader_elected`)

- [ ] **Step 1: Write failing tests for Requirer databag writes**

Update existing tests and add new ones in `tests/unit/test_requirer.py`:

Update `test_app_databag_written_on_joined_by_leader`:
```python
    def test_app_databag_written_on_joined_by_leader(self):
        """On relation-joined, the leader writes model-name and application-name to the app databag."""
        ctx = ops.testing.Context(RequirerCharm, meta=RequirerCharm.META)
        relation = ops.testing.Relation(
            endpoint="role-assignment",
            interface="role-assignment",
        )
        state = ops.testing.State(relations=[relation], leader=True)
        out = ctx.run(ctx.on.relation_joined(relation), state)
        rel = out.get_relation(relation.id)
        local_app_data = rel.local_app_data
        assert "model-name" in local_app_data
        assert "application-name" in local_app_data
        assert local_app_data["application-name"] == "test-requirer"
```

Add a test for `machine-id` not being written (it requires ops 3.5.1 and is optional — the library should only write it when available). For now, the library does NOT write `machine-id` since that depends on the ops version providing the juju context class. Add a placeholder test that documents the current behavior:

```python
    def test_unit_databag_does_not_write_machine_id_by_default(self):
        """machine-id is not written if the unit does not provide it.

        Writing machine-id depends on the charm explicitly providing it
        or on ops >= 3.5.1 with the juju context class. The library
        does not auto-detect this.
        """
        ctx = ops.testing.Context(RequirerCharm, meta=RequirerCharm.META)
        relation = ops.testing.Relation(
            endpoint="role-assignment",
            interface="role-assignment",
        )
        state = ops.testing.State(relations=[relation])
        out = ctx.run(ctx.on.relation_joined(relation), state)
        rel = out.get_relation(relation.id)
        assert "machine-id" not in rel.local_unit_data
```

Add a test for `leader_elected` writing `application-name`:

```python
    def test_leader_elected_writes_application_name(self):
        """When a unit becomes leader with an existing relation, application-name is written."""
        ctx = ops.testing.Context(RequirerCharm, meta=RequirerCharm.META)
        relation = ops.testing.Relation(
            endpoint="role-assignment",
            interface="role-assignment",
        )
        state = ops.testing.State(relations=[relation], leader=True)
        out = ctx.run(ctx.on.leader_elected(), state)
        rel = out.get_relation(relation.id)
        local_app_data = rel.local_app_data
        assert "model-name" in local_app_data
        assert "application-name" in local_app_data
        assert local_app_data["application-name"] == "test-requirer"
```

- [ ] **Step 2: Run tests to verify the `application-name` test fails**

Run: `tox -e unit -- tests/unit/test_requirer.py::TestRequirerRegistration -v`
Expected: FAIL — `application-name` not written to app databag

- [ ] **Step 3: Update Requirer `_on_relation_joined` and `_on_leader_elected`**

In `lib/charms/role_distributor/v0/role_assignment.py`:

Update `_on_relation_joined` (lines 237-244):
```python
    def _on_relation_joined(self, event: ops.RelationJoinedEvent) -> None:
        event.relation.data[self._charm.unit]["unit-name"] = (
            self._charm.unit.name
        )
        if self._charm.unit.is_leader():
            event.relation.data[self._charm.app]["model-name"] = (
                self.model.name
            )
            event.relation.data[self._charm.app]["application-name"] = (
                self._charm.app.name
            )
```

Update `_on_leader_elected` (lines 260-263):
```python
    def _on_leader_elected(self, event: ops.LeaderElectedEvent) -> None:
        relation = self._relation()
        if relation is not None:
            relation.data[self._charm.app]["model-name"] = self.model.name
            relation.data[self._charm.app]["application-name"] = (
                self._charm.app.name
            )
```

**Deliberate deviation from spec:** The spec's library section says the library handles writing `machine-id` (when available) automatically on `relation-joined`. This plan intentionally defers that behavior: auto-detecting the ops 3.5.1 juju context API requires investigation that is out of scope for this task. For now, `machine-id` is NOT auto-written by the library. Charm authors that want to provide `machine-id` should write it to their unit databag themselves. A follow-up task should add auto-detection once the ops 3.5.1 API is confirmed.

- [ ] **Step 4: Run tests to verify they pass**

Run: `tox -e unit -- tests/unit/test_requirer.py::TestRequirerRegistration -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add lib/charms/role_distributor/v0/role_assignment.py tests/unit/test_requirer.py
git commit -m "feat(library): write application-name to Requirer App databag"
```

---

### Task 5: Update `RoleAssignmentChangedEvent` to carry `workload_params`

**Files:**
- Test: `tests/unit/test_requirer.py`
- Modify: `lib/charms/role_distributor/v0/role_assignment.py:139-179` (event class), `246-255` (emission)

- [ ] **Step 1: Write failing tests for `workload_params` in changed event**

Update `RequirerCharm._on_changed` to capture `workload_params`:

```python
    def _on_changed(self, event: RoleAssignmentChangedEvent):
        _events_received.append(
            ("changed", event.status, event.roles, event.message, event.workload_params)
        )
```

Update `test_changed_event_emitted_on_new_assignment` to expect the new tuple shape:

```python
    def test_changed_event_emitted_on_new_assignment(self):
        """RoleAssignmentChangedEvent fires when assignment appears."""
        ctx = ops.testing.Context(RequirerCharm, meta=RequirerCharm.META)
        assignments = {
            "test-requirer/0": {"status": "assigned", "roles": ["control"]}
        }
        relation = ops.testing.Relation(
            endpoint="role-assignment",
            interface="role-assignment",
            remote_app_data={"assignments": json.dumps(assignments)},
        )
        state = ops.testing.State(relations=[relation])
        ctx.run(ctx.on.relation_changed(relation), state)
        assert len(_events_received) == 1
        assert _events_received[0] == ("changed", "assigned", ("control",), None, None)
```

Add a test with `workload-params`:

```python
    def test_changed_event_with_workload_params(self):
        """RoleAssignmentChangedEvent carries workload_params when present."""
        ctx = ops.testing.Context(RequirerCharm, meta=RequirerCharm.META)
        assignments = {
            "test-requirer/0": {
                "status": "assigned",
                "roles": ["gateway"],
                "workload-params": {"flavors": ["rgw"]},
            }
        }
        relation = ops.testing.Relation(
            endpoint="role-assignment",
            interface="role-assignment",
            remote_app_data={"assignments": json.dumps(assignments)},
        )
        state = ops.testing.State(relations=[relation])
        ctx.run(ctx.on.relation_changed(relation), state)
        assert len(_events_received) == 1
        assert _events_received[0] == (
            "changed", "assigned", ("gateway",), None, {"flavors": ["rgw"]}
        )
```

Update `test_changed_event_always_emitted` and `test_error_assignment_surfaces_message` to expect the 5-element tuple:

```python
    def test_changed_event_always_emitted(self):
        """The library is stateless — changed fires on every relation-changed
        that carries a valid assignment. Charms handle their own idempotency."""
        ctx = ops.testing.Context(RequirerCharm, meta=RequirerCharm.META)
        assignments = {
            "test-requirer/0": {"status": "assigned", "roles": ["control"]}
        }
        relation = ops.testing.Relation(
            endpoint="role-assignment",
            interface="role-assignment",
            remote_app_data={"assignments": json.dumps(assignments)},
        )
        state = ops.testing.State(relations=[relation])
        ctx.run(ctx.on.relation_changed(relation), state)
        assert len(_events_received) == 1
        assert _events_received[0] == ("changed", "assigned", ("control",), None, None)
```

```python
    def test_error_assignment_surfaces_message(self):
        """Error assignment includes the message in the event."""
        ctx = ops.testing.Context(RequirerCharm, meta=RequirerCharm.META)
        assignments = {
            "test-requirer/0": {
                "status": "error",
                "message": "not in topology",
            }
        }
        relation = ops.testing.Relation(
            endpoint="role-assignment",
            interface="role-assignment",
            remote_app_data={"assignments": json.dumps(assignments)},
        )
        state = ops.testing.State(relations=[relation])
        ctx.run(ctx.on.relation_changed(relation), state)
        assert len(_events_received) == 1
        assert _events_received[0] == (
            "changed", "error", (), "not in topology", None
        )
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `tox -e unit -- tests/unit/test_requirer.py -v`
Expected: FAIL — `RoleAssignmentChangedEvent` has no `workload_params`

- [ ] **Step 3: Update `RoleAssignmentChangedEvent`**

In `lib/charms/role_distributor/v0/role_assignment.py`, update `RoleAssignmentChangedEvent` (lines 139-178):

```python
class RoleAssignmentChangedEvent(ops.RelationEvent):
    """Emitted on the Requirer when this unit's assignment changes."""

    def __init__(
        self,
        handle,
        relation,
        status: str,
        roles: tuple[str, ...],
        message: str | None,
        workload_params: dict[str, Any] | None,
    ):
        super().__init__(handle, relation)
        self._status = status
        self._roles = roles
        self._message = message
        self._workload_params = workload_params

    @property
    def status(self) -> str:
        return self._status

    @property
    def roles(self) -> tuple[str, ...]:
        return self._roles

    @property
    def message(self) -> str | None:
        return self._message

    @property
    def workload_params(self) -> dict[str, Any] | None:
        return self._workload_params

    def snapshot(self) -> dict:
        d = super().snapshot()
        d["status"] = self._status
        d["roles"] = list(self._roles)
        d["message"] = self._message
        d["workload_params"] = self._workload_params
        return d

    def restore(self, snapshot: dict) -> None:
        super().restore(snapshot)
        self._status = snapshot["status"]
        self._roles = tuple(snapshot["roles"])
        self._message = snapshot["message"]
        self._workload_params = snapshot["workload_params"]
```

- [ ] **Step 4: Update Requirer event emission**

In `_on_relation_changed` (lines 246-255), update the emit call:

```python
    def _on_relation_changed(self, event: ops.RelationChangedEvent) -> None:
        assignment = self._read_assignment(event.relation)
        if assignment is None:
            return
        self.on.role_assignment_changed.emit(
            event.relation,
            assignment.status,
            assignment.roles,
            assignment.message,
            assignment.workload_params,
        )
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `tox -e unit -- tests/unit/test_requirer.py -v`
Expected: ALL PASS

- [ ] **Step 6: Commit**

```bash
git add lib/charms/role_distributor/v0/role_assignment.py tests/unit/test_requirer.py
git commit -m "feat(library): add workload_params to RoleAssignmentChangedEvent"
```

---

### Task 6: Update Provider `set_assignments` test for `workload-params`

**Files:**
- Test: `tests/unit/test_provider.py`

- [ ] **Step 1: Update `test_set_assignments_writes_to_app_databag`**

In `tests/unit/test_provider.py`, update the `WriterCharm._on_changed` inside `test_set_assignments_writes_to_app_databag` to include an assignment with `workload_params`:

```python
    def test_set_assignments_writes_to_app_databag(self):
        """set_assignments serializes assignment map including workload-params."""
        class WriterCharm(ops.CharmBase):
            META = ProviderCharm.META

            def __init__(self, framework):
                super().__init__(framework)
                self.role_assignment = RoleAssignmentProvider(self, "role-assignment")
                self.framework.observe(
                    self.on["role-assignment"].relation_changed,
                    self._on_changed,
                )

            def _on_changed(self, event):
                rel = self.model.get_relation("role-assignment")
                if rel:
                    self.role_assignment.set_assignments(
                        rel,
                        {
                            "microceph/0": UnitRoleAssignment(
                                status="assigned",
                                roles=("control", "gateway"),
                                workload_params={"flavors": ["rgw"]},
                            ),
                            "microceph/1": UnitRoleAssignment(status="pending"),
                        },
                    )

        ctx = ops.testing.Context(WriterCharm, meta=WriterCharm.META)
        relation = ops.testing.Relation(
            endpoint="role-assignment",
            interface="role-assignment",
        )
        state = ops.testing.State(relations=[relation], leader=True)
        out = ctx.run(ctx.on.relation_changed(relation), state)
        out_rel = out.get_relation(relation.id)
        raw = out_rel.local_app_data.get("assignments")
        assert raw is not None
        parsed = json.loads(raw)
        assert parsed["microceph/0"] == {
            "status": "assigned",
            "roles": ["control", "gateway"],
            "workload-params": {"flavors": ["rgw"]},
        }
        assert parsed["microceph/1"] == {"status": "pending"}
```

- [ ] **Step 2: Run tests to verify they pass**

Run: `tox -e unit -- tests/unit/test_provider.py::TestProviderSetAssignments -v`
Expected: ALL PASS (this should pass immediately since `to_dict()` was updated in Task 1)

- [ ] **Step 3: Commit**

```bash
git add tests/unit/test_provider.py
git commit -m "test(provider): update set_assignments test for workload-params"
```

---

### Task 7: Run full test suite and linting

**Files:** All modified files

- [ ] **Step 1: Run full unit tests**

Run: `tox -e unit`
Expected: ALL PASS

- [ ] **Step 2: Run linting**

Run: `tox -e lint`
Expected: PASS

- [ ] **Step 3: Run type checking**

Run: `tox -e static`
Expected: PASS (may need to add `Any` to pyright includes or adjust config)

- [ ] **Step 4: Fix any issues found**

Address any lint, type, or test failures.

- [ ] **Step 5: Commit any fixes**

```bash
git add -u
git commit -m "chore: fix lint and type issues from library update"
```
