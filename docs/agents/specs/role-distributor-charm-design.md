# Role Distributor Charm — Design Spec

## Overview

The `role-distributor` charm is a Juju machine charm that acts as a central coordinator
for distributing roles to related applications. The operator provides a YAML config blob
with machine-level and unit-level role mappings, and the charm resolves and publishes
per-unit assignments to all related applications through the `role-assignment` interface.

The interface library (`lib/charms/role_distributor/v0/role_assignment.py`) is already
fully implemented. This design covers the remaining work: charm implementation, business
logic module, tooling modernisation, tests, and CI.

---

## 1. Library — Current State (no changes needed)

The library has been fully updated with the spec overhaul. Current API:

```python
@dataclass(frozen=True)
class UnitRoleAssignment:
    status: Literal["assigned", "pending", "error"]
    roles: tuple[str, ...] = ()
    message: str | None = None
    workload_params: dict[str, Any] | None = None

@dataclass(frozen=True)
class RegisteredUnit:
    unit_name: str
    model_name: str
    application_name: str
    machine_id: str | None = None
```

All custom events, Provider, and Requirer classes are updated and tested. No library
changes are needed for the charm implementation.

---

## 2. Config Schema

### YAML blob format (charm config option `role-mapping`)

The config supports two levels of mapping: **machine-level** and **unit-level**.
Resolution follows the precedence rules from the spec.

```yaml
machines:
  "0":
    roles: [control, storage, network]
    workload-params:
      microceph:
        flavors: [rgw]
      microovn:
        some-key: some-value
  "1":
    roles: [storage, network]
units:
  microceph/0:
    roles: [control, storage, gateway]  # overrides machine-level roles entirely
    workload-params:
      flavors: [rgw, s3]  # shallow-merges with machine-level microceph params
```

**Structure:**

- `machines` (optional): dict keyed by machine ID (string).
  - `roles` (list of str): roles assigned to all units on this machine (unless
    overridden at unit level).
  - `workload-params` (optional dict): keyed by application name, since multiple
    apps share a machine. Each value is a dict of params for that app's units.
- `units` (optional): dict keyed by unit name (e.g. `microceph/0`).
  - `roles` (list of str): roles for this specific unit. Fully replaces machine-level
    roles if both exist.
  - `workload-params` (optional dict): params for this unit. Shallow-merges with
    machine-level params (unit keys override machine keys).

At least one of `machines` or `units` must be present.

### Resolution precedence (from spec)

1. **Roles:** Unit-level fully replaces machine-level. No merging.
2. **`workload-params`:** Shallow merge. Machine-level params (scoped by application
   name) form the base, unit-level params override individual keys.
3. Units without `machine-id` only receive unit-level config. Machine-level config
   is silently skipped for them.

### charmcraft.yaml declaration

```yaml
config:
  options:
    role-mapping:
      type: string
      default: ""
      description: |
        YAML blob defining role assignments. Supports machine-level and
        unit-level mappings with resolution precedence. See charm docs
        for the full schema.
```

---

## 3. Business Logic Module — `src/role_distributor.py`

Replaces the current stubs. Two data structures and two functions:

### `MachineConfig`

```python
@dataclass(frozen=True)
class MachineConfig:
    roles: tuple[str, ...]
    workload_params: dict[str, dict[str, Any]]  # keyed by application name
```

### `UnitConfig`

```python
@dataclass(frozen=True)
class UnitConfig:
    roles: tuple[str, ...]
    workload_params: dict[str, Any]
```

### `parse_config(yaml_string: str) -> ParsedConfig`

Where `ParsedConfig` is:

```python
@dataclass(frozen=True)
class ParsedConfig:
    machines: dict[str, MachineConfig]   # machine_id -> config
    units: dict[str, UnitConfig]         # unit_name -> config
```

- Parses the YAML string.
- Validates structure: `machines` and/or `units` dicts, correct nested types.
- Raises `ValueError` on malformed input (empty string, bad YAML, wrong types,
  neither `machines` nor `units` present).

### `compute_assignments(config: ParsedConfig, registered_units: list[RegisteredUnit]) -> dict[str, UnitRoleAssignment]`

Only produces entries for units in the `registered_units` input. For each registered unit:

1. Look up unit-level config: `config.units.get(unit.unit_name)`.
2. Look up machine-level config: `config.machines.get(unit.machine_id)` if
   `unit.machine_id` is not None.
3. **Resolve roles:** unit-level roles if present, else machine-level roles, else no match.
4. **Resolve workload-params:** start with machine-level params scoped to
   `unit.application_name` (if available), then shallow-merge unit-level params on top.
5. If resolved → `UnitRoleAssignment(status="assigned", roles=..., workload_params=...)`.
   `workload_params` is `None` if the resolved dict is empty.
6. If no match → `UnitRoleAssignment(status="pending")`.

Returns the assignments dict keyed by unit name. The charm derives the unmatched
count by filtering for `status="pending"` entries.

---

## 4. Charm Class — `src/charm.py`

### `RoleDistributorCharm(ops.CharmBase)`

**Constructor:**
- Instantiate `RoleAssignmentProvider(self, "role-assignment")`.
- Observe: `config-changed`, `relation-changed` on `role-assignment`,
  `relation-departed` on `role-assignment`, `leader-elected`.

The charm observes raw relation events rather than the library's semantic events
(`unit_registered`, `unit_departed`) because `_reconcile()` re-reads all state
from scratch anyway. This avoids N redundant reconcile cycles when the library
emits `unit_registered` for every unit on every `relation-changed`.

`leader-elected` is observed directly to ensure the new leader re-publishes
assignments on all relations.

**All handlers funnel to `_reconcile()`:**

```
_reconcile():
  1. If not leader → return (only leader writes to app databag).
  2. Read "role-mapping" config. If empty → BlockedStatus("no role-mapping config provided").
  3. parse_config(). If ValueError → BlockedStatus("invalid role-mapping config: {error}").
  4. For each relation on "role-assignment" endpoint:
     a. provider.get_registered_units(relation)
     b. compute_assignments(parsed_config, registered_units)
     c. provider.set_assignments(relation, assignments)
  5. Count pending units (status="pending") across all relations.
  6. If any pending → WaitingStatus("units awaiting assignment: {count}").
  7. Else → ActiveStatus().
```

No install/start/workload logic — this charm has no workload process.

---

## 5. `charmcraft.yaml`

```yaml
name: role-distributor
type: charm
summary: Distributes roles to related applications via operator-defined mapping
description: |
  A Juju machine charm that acts as a central role distributor. The operator
  provides a YAML mapping of machines and units to roles via config, and the
  charm resolves and publishes assignments to all related applications through
  the role-assignment interface. Supports machine-level and unit-level config
  with precedence rules for roles and workload parameters.

base: ubuntu@24.04
platforms:
  amd64:

parts:
  charm:
    plugin: charm
    source: .
    charm-requirements: [requirements.txt]

provides:
  role-assignment:
    interface: role-assignment

config:
  options:
    role-mapping:
      type: string
      default: ""
      description: |
        YAML blob defining role assignments. Supports machine-level and
        unit-level mappings with resolution precedence. See charm docs
        for the full schema.
```

---

## 6. Tooling Configuration

### `pyproject.toml`

- `uv` as package manager with `[dependency-groups]`: dev (ruff, ty, pre-commit),
  test (pytest, ops[testing], coverage), integration (pytest, jubilant>=1.0).
- `ops` as sole runtime dependency (unbounded).
- Ruff: line-length 99, Google-style pydocstyle, select E/W/F/I/UP/B/SIM/RUF/D.
- `ty`: python-version 3.10.
- pytest: testpaths `tests/unit`, coverage source `src`, fail_under 80.
- Build system: setuptools>=75.

### `tox.ini`

- tox 4 with tox-uv, `runner = uv-venv-runner`.
- Environments: `lint` (ruff check + format --check + ty check), `format` (ruff fix + format),
  `unit` (coverage + pytest), `integration` (pytest + jubilant).

### `.pre-commit-config.yaml`

- `ruff-pre-commit`: ruff-check (--fix) + ruff-format.
- `uv-pre-commit`: uv-lock.
- `ty` pre-commit hook.

---

## 7. Tests

### Unit tests — `tests/unit/test_charm.py` (rewrite)

Using `ops.testing` (Scenario):
- No config → BlockedStatus.
- Invalid YAML → BlockedStatus with error message.
- Valid config with machine-level mapping, matched units → ActiveStatus, correct
  assignments in databag.
- Valid config with unit-level mapping, matched units → ActiveStatus.
- Mixed machine + unit config with resolution precedence → correct merged assignments.
- Partial matches → WaitingStatus with count.
- Units without machine-id skip machine-level config.
- Non-leader does not write to app databag.
- Relation events (relation-changed, relation-departed) trigger reconcile.
- leader-elected triggers reconcile.

### Unit tests — `tests/unit/test_role_distributor.py` (new)

`parse_config`:
- Valid YAML with machines only, units only, both.
- Empty string → ValueError.
- Malformed YAML → ValueError.
- Missing required keys → ValueError.
- Wrong types → ValueError.

`compute_assignments`:
- Machine-level only: unit with machine-id gets roles.
- Unit-level only: unit matched by name gets roles.
- Both levels: unit-level roles replace machine-level.
- Workload-params: machine-level scoped by app name, shallow-merged with unit-level.
- Workload-params resolves to `None` when resolved dict is empty.
- Unit without machine-id: machine-level config skipped.
- No match → pending.
- Multi-model scenario.
- Unknown top-level keys in YAML → ValueError.

### Existing library tests — no changes needed

Library tests already cover `workload_params`, `application_name`, `machine_id`.

### Integration tests — `tests/integration/` (rewrite to Jubilant)

- `conftest.py`: `jubilant.temp_model()` fixture, `charm()` fixture for .charm path.
- `test_charm.py`: deploy → blocked (no config) → set role-mapping config → active.

---

## 8. CI Workflows

### `.github/workflows/ci.yaml` — push/PR

- `ubuntu-24.04`, `astral-sh/setup-uv@v5`.
- Jobs: `lint` (tox -e lint), `unit` (tox -e unit + coverage artifact).

### `.github/workflows/integration.yaml` — manual + nightly

- `ubuntu-24.04`, Concierge snap, `concierge prepare --preset machine --extra-snaps astral-uv`.
- `charmcraft pack`, `tox -e integration`.

### `.github/workflows/release.yaml` — tag `v*`

- `charmcraft pack` + `charmcraft upload` + `charmcraft release`.

---

## 9. README.md

Replace placeholder with:
- One-paragraph description.
- Quick Start: deploy command, example `role-mapping` config showing both machine
  and unit level mappings.
- Development: `uv sync`, `tox -e lint`, `tox -e unit`, `pre-commit install`.

---

## Summary of changes by file

| File | Action |
|------|--------|
| `src/charm.py` | Rewrite: Provider integration, reconcile loop, status management |
| `src/role_distributor.py` | Rewrite: `parse_config()`, `compute_assignments()` with resolution logic |
| `charmcraft.yaml` | Update: base, provides endpoint, config option, description |
| `pyproject.toml` | Rewrite: uv, dependency-groups, ruff/ty config |
| `tox.ini` | Rewrite: tox-uv based |
| `.pre-commit-config.yaml` | New |
| `tests/unit/test_charm.py` | Rewrite: full reconcile coverage including resolution |
| `tests/unit/test_role_distributor.py` | New: parse_config, compute_assignments tests |
| `tests/integration/conftest.py` | New: Jubilant fixtures |
| `tests/integration/test_charm.py` | Rewrite: Jubilant-based |
| `.github/workflows/ci.yaml` | New |
| `.github/workflows/integration.yaml` | New |
| `.github/workflows/release.yaml` | New |
| `README.md` | Rewrite |
