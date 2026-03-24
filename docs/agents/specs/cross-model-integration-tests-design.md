# Cross-Model Integration Tests Design

## Problem

The current integration tests only verify that the role-distributor charm deploys and
accepts config. There is no testing of the relation protocol — the core value of this
charm. A requirer charm consuming role assignments cross-model is entirely untested.

## Goals

- Test the full end-to-end flow: provider publishes assignments, requirer receives them
  across a Juju cross-model relation (`juju offer` / `juju consume`).
- Exercise multiple requirer applications with multiple units to validate app-scoped
  workload-params, machine-level vs unit-level role resolution, and scale-up behavior.
- Keep the test infrastructure self-contained in this repo.

## Non-Goals

- Testing the requirer lib in isolation (already covered by unit tests).
- Testing Juju's cross-model relation machinery itself — we trust Juju, we just need to
  verify our charm works through it.
- Performance or load testing.
- Testing the `error` status path — `compute_assignments` currently only produces
  `assigned` and `pending`, never `error`. This can be added later if the business logic
  evolves.

## Design

### Dummy Requirer Charm

A minimal machine charm at `tests/integration/charms/dummy-requirer/`.

**Metadata (`charmcraft.yaml`):**

- Machine charm, base `ubuntu@24.04`, platform `amd64`.
- `requires: role-assignment: interface: role-assignment` with `limit: 1`.
- Declares the `get-assignment` action inline (no separate `actions.yaml`).
- Includes a `parts` section using the `uv` plugin (matching the main charm's build
  approach) to install `ops` from `requirements.txt`.

**Charm code (`src/charm.py`, ~100 lines):**

- Uses `RoleAssignmentRequirer` from the copied lib.
- On `relation-joined`, explicitly writes `machine-id` to the unit databag by reading
  `JUJU_MACHINE_ID` from the environment. The `RoleAssignmentRequirer` lib only writes
  `unit-name` automatically — `machine-id` is the charm's responsibility.
- On `role_assignment_changed`:
  - Validates: status is `"assigned"`, roles list is non-empty.
  - Sets `ActiveStatus("roles: <comma-separated roles>")`.
  - If validation fails, sets `BlockedStatus("invalid assignment: <details>")`.
- On `role_assignment_revoked`: sets `WaitingStatus("no assignment")`.
- Initial state (no relation): `WaitingStatus("no assignment")`.
- `get-assignment` action: returns the full assignment as JSON (status, roles,
  workload-params). This allows precise assertions on workload-params that cannot be
  expressed through status messages alone.

**Lib copying:**

The `role_assignment.py` lib must be physically copied into the dummy charm's
`lib/charms/role_distributor/v0/` directory before packing, because `charmcraft pack`
runs inside a LXD container that cannot follow symlinks or access paths outside the
charm directory.

### Build Target

A tox target `build-dummy` that:

1. Copies `lib/charms/role_distributor/v0/role_assignment.py` (and its parent
   `__init__.py` files for the package hierarchy) into
   `tests/integration/charms/dummy-requirer/lib/charms/role_distributor/v0/`.
2. Runs `charmcraft pack` in `tests/integration/charms/dummy-requirer/`.
3. Outputs the `.charm` file in the dummy charm directory.

This is a manual pre-step — run `tox -e build-dummy` before `tox -e integration`.
The integration tox target does not auto-invoke it.

### Test Infrastructure

**New fixtures in `tests/integration/conftest.py`:**

- `provider_model` (module-scoped): `jubilant.temp_model()` for the role-distributor.
- `requirer_model` (module-scoped): a second `jubilant.temp_model()` for the dummy
  requirers.
- `dummy_charm` (session-scoped): resolves the dummy `.charm` file path via
  `DUMMY_CHARM_PATH` env var or auto-detection from
  `tests/integration/charms/dummy-requirer/*.charm`.
- Helper to wire cross-model relations: `juju offer` on the provider model, `juju
  consume` + `juju integrate` on the requirer model.

**Cross-model relation wiring pattern:**

```python
provider_model_name = provider_juju.status().model.name
provider_juju.offer(f"{provider_model_name}.role-distributor", endpoint="role-assignment")
requirer_juju.consume(f"{provider_model_name}.role-distributor")
requirer_juju.integrate("app-a", "role-distributor")
requirer_juju.integrate("app-b", "role-distributor")
```

The `offer` and `consume` APIs require model-qualified app names. The provider model
name is discovered dynamically from `juju status`.

**Existing tests** (`test_charm.py`) remain unchanged, using the current single-model
`juju` fixture.

**New test module:** `tests/integration/test_cross_model.py`.

**Test ordering:** Tests are structured as methods within a single test class to
guarantee execution order (pytest executes methods top-to-bottom within a class). No
additional dependency needed.

**Wait timeouts:** All `juju.wait()` calls use a module-level timeout constant
(e.g., 15 minutes for deploys, 5 minutes for config changes) to prevent hanging CI.

**Teardown order:** Cross-model relations are removed before models are destroyed.
The requirer model is torn down before the provider model to avoid dangling offer
references.

**Unit-level assertions:** Tests 3, 5, and 7 require checking individual unit statuses
rather than app-level `all_active`/`all_waiting`. These use custom `wait` predicates
that inspect `status.get_units("<app>")` for per-unit workload status checks.

### Test Scenarios

All tests run in order within the module (methods in a single test class), sharing
module-scoped models (state carries across tests).

#### 1. `test_deploy_and_relate_cross_model`

- Deploy role-distributor in the provider model.
- Deploy two dummy-requirer apps in the requirer model: `app-a` (2 units) and `app-b`
  (1 unit).
- Offer the `role-assignment` endpoint from the provider model.
- Consume and integrate both apps in the requirer model.
- Assert: role-distributor is `BlockedStatus` (no config set yet), all dummy
  requirer units are `WaitingStatus("no assignment")`.

#### 2. `test_machine_level_assignment`

- Query `juju status` on the requirer model to discover machine-ids for all units.
- Set `role-mapping` config on role-distributor with machine-level roles mapping those
  machine-ids (e.g., machine X gets `[control]`, machine Y gets `[compute]`).
- Wait for all dummy-requirer units to reach `ActiveStatus` with expected roles in their
  status messages.
- Assert: role-distributor reaches `ActiveStatus`.

#### 3. `test_unit_level_override`

- Update `role-mapping` config to add a unit-level override for `app-a/0` with a
  different role (e.g., `[storage]`).
- Assert (unit-level predicate): `app-a/0` status message changes to `"roles: storage"`.
- Assert (unit-level predicate): other units keep their machine-level roles.

#### 4. `test_workload_params_app_scoping`

- Update config with app-scoped workload-params on a machine entry.
- Run `get-assignment` action on units from both apps.
- Assert: each app receives only its own scoped workload-params.

#### 5. `test_unmatched_unit_pending`

- Scale `app-b` to 2 units in the requirer model.
- The new unit's machine-id is not in the config.
- Assert (unit-level predicate): the new unit stays `WaitingStatus`.
- Assert: role-distributor shows `WaitingStatus` mentioning units awaiting assignment.

#### 6. `test_scale_up_assigns_new_unit`

- Query the new unit's machine-id from `juju status`.
- Update config to include that machine-id with roles.
- Assert: new unit reaches `ActiveStatus` with correct roles.
- Assert: role-distributor returns to `ActiveStatus`.

#### 7. `test_relation_removal`

- Remove the cross-model relation for `app-b` from the requirer model:
  `requirer_juju.remove_relation("app-b", "role-distributor")`.
- Assert (unit-level predicate): `app-b` units go to `WaitingStatus("no assignment")`.
- Assert: role-distributor stays `ActiveStatus` (app-a is still fully assigned).

## Files to Create

- `tests/integration/charms/dummy-requirer/charmcraft.yaml` (includes action declaration)
- `tests/integration/charms/dummy-requirer/src/charm.py`
- `tests/integration/charms/dummy-requirer/requirements.txt`
- `tests/integration/test_cross_model.py`

## Files to Modify

- `tests/integration/conftest.py` — add cross-model fixtures and dummy_charm fixture
- `tox.ini` — add `build-dummy` target
- `pyproject.toml` — no changes expected (jubilant already in integration deps)
