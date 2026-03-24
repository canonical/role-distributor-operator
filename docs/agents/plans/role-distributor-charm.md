# Role Distributor Charm Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the role-distributor charm: business logic module, charm class, tooling, tests, CI, and docs.

**Architecture:** The charm uses Approach 2 from the design: `src/role_distributor.py` contains the config parsing and resolution logic (`parse_config`, `compute_assignments`), while `src/charm.py` is a thin orchestrator that instantiates `RoleAssignmentProvider` from the existing library and funnels all events to a single `_reconcile()` method. The library (already complete in `lib/`) handles all relation databag plumbing.

**Tech Stack:** Python 3.10+, ops framework, PyYAML (for config parsing), uv (package manager), tox 4 + tox-uv, ruff + ty (linting/typing), ops.testing (unit tests), jubilant (integration tests).

**Design spec:** `docs/specs/2026-03-24-role-distributor-charm-design.md`
**Interface spec:** `docs/specs/2026-03-18-role-assignment-interface-design.md`
**Library (read-only):** `lib/charms/role_distributor/v0/role_assignment.py`

---

## File Structure

| File | Responsibility | Action |
|------|---------------|--------|
| `src/role_distributor.py` | Config parsing + resolution logic | Rewrite |
| `src/charm.py` | Charm lifecycle, reconcile loop | Rewrite |
| `tests/unit/test_role_distributor.py` | Tests for parse_config, compute_assignments | Create |
| `tests/unit/test_charm.py` | Tests for charm reconcile behaviour | Rewrite |
| `charmcraft.yaml` | Charm metadata, relations, config | Rewrite |
| `pyproject.toml` | Project config, deps, tool settings | Rewrite |
| `tox.ini` | Test environments | Rewrite |
| `requirements.txt` | Runtime deps for charmcraft | Update |
| `.pre-commit-config.yaml` | Pre-commit hooks | Create |
| `.github/workflows/ci.yaml` | Lint + unit CI | Create |
| `.github/workflows/integration.yaml` | Integration test CI | Create |
| `.github/workflows/release.yaml` | Release CI | Create |
| `tests/integration/conftest.py` | Jubilant fixtures | Create |
| `tests/integration/test_charm.py` | Integration tests | Rewrite |
| `README.md` | Project docs | Rewrite |

---

### Task 1: Tooling and Project Configuration

**Files:**
- Rewrite: `pyproject.toml`
- Rewrite: `tox.ini`
- Update: `requirements.txt`
- Rewrite: `charmcraft.yaml`
- Create: `.pre-commit-config.yaml`

This task replaces the template tooling with the uv-based setup from the design spec. No code changes yet — just config files.

- [ ] **Step 1: Rewrite `pyproject.toml`**

Replace the entire file with:

```python
# pyproject.toml
[project]
name = "role-distributor"
version = "0.0.1"
requires-python = ">=3.10"
description = "Juju charm that distributes roles to related applications"

dependencies = [
    "ops",
    "pyyaml",
]

[dependency-groups]
dev = ["ruff", "ty", "pre-commit"]
test = ["pytest", "ops[testing]", "coverage[toml]"]
integration = ["pytest", "jubilant>=1.0"]

[build-system]
requires = ["setuptools>=75"]
build-backend = "setuptools.build_meta"

[tool.ruff]
line-length = 99
target-version = "py310"

[tool.ruff.lint]
select = [
    "E", "W",       # pycodestyle
    "F",             # pyflakes
    "I",             # isort
    "UP",            # pyupgrade
    "B",             # flake8-bugbear
    "SIM",           # flake8-simplify
    "RUF",           # ruff-specific
    "D",             # pydocstyle (Google convention)
]
ignore = ["D100", "D104", "D107"]  # module/package/init docstrings optional
extend-per-file-ignores = {"tests/*" = ["D100", "D101", "D102", "D103", "D104"]}

[tool.ruff.lint.pydocstyle]
convention = "google"

[tool.ruff.format]
quote-style = "double"

[tool.ty]
python-version = "3.10"

[tool.pytest.ini_options]
minversion = "8.0"
testpaths = ["tests/unit"]

[tool.coverage.run]
source = ["src"]
branch = true

[tool.coverage.report]
show_missing = true
fail_under = 80
```

- [ ] **Step 2: Rewrite `tox.ini`**

Replace the entire file with:

```ini
[tox]
requires =
    tox>=4.23
    tox-uv>=1.25
env_list = lint, unit

[testenv]
runner = uv-venv-runner
package = editable
set_env =
    PYTHONPATH = {tox_root}/lib:{tox_root}/src

[testenv:lint]
description = run linters (ruff + ty)
skip_install = true
deps =
    ruff
    ty
commands =
    ruff check {posargs:src tests lib}
    ruff format --check {posargs:src tests lib}
    ty check src

[testenv:format]
description = auto-fix lint + format
skip_install = true
deps = ruff
commands =
    ruff check --fix {posargs:src tests lib}
    ruff format {posargs:src tests lib}

[testenv:unit]
description = run unit tests with coverage
dependency_groups = test
commands =
    coverage run -m pytest {posargs:tests/unit}
    coverage report

[testenv:integration]
description = run integration tests
dependency_groups = integration
commands =
    pytest {posargs:tests/integration} -v --tb=short
```

- [ ] **Step 3: Update `requirements.txt`**

Replace with:

```
ops
pyyaml
```

`pyyaml` is needed because the charm parses YAML config blobs. No version pin on ops.

- [ ] **Step 4: Rewrite `charmcraft.yaml`**

Replace the entire file with:

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

- [ ] **Step 5: Create `.pre-commit-config.yaml`**

```yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.15.7
    hooks:
      - id: ruff-check
        args: [--fix]
      - id: ruff-format

  - repo: https://github.com/astral-sh/uv-pre-commit
    rev: 0.11.0
    hooks:
      - id: uv-lock

  - repo: https://github.com/astral-sh/ty
    rev: 0.0.1a14
    hooks:
      - id: ty
```

- [ ] **Step 6: Run `uv lock` to generate lock file**

Run: `uv lock`
Expected: `uv.lock` file created with no errors.

- [ ] **Step 7: Verify lint passes on existing library code**

Run: `uv run tox -e lint`
Expected: May have lint issues in existing files — note them but do not fix in this task. The library in `lib/` and `src/` files will be rewritten in later tasks.

- [ ] **Step 8: Commit**

```bash
git add pyproject.toml tox.ini requirements.txt charmcraft.yaml .pre-commit-config.yaml uv.lock
git commit -m "ci: modernise tooling to uv + tox-uv + ruff + ty"
```

---

### Task 2: Business Logic — Data Structures and `parse_config`

**Files:**
- Create: `tests/unit/test_role_distributor.py`
- Rewrite: `src/role_distributor.py`

**Context:** The config YAML has this structure:

```yaml
machines:
  "0":
    roles: [control, storage]
    workload-params:
      microceph:
        flavors: [rgw]
units:
  microceph/0:
    roles: [control, gateway]
    workload-params:
      flavors: [rgw, s3]
```

`parse_config` parses this into typed dataclasses. `compute_assignments` is Task 3.

- [ ] **Step 1: Write failing tests for data classes and `parse_config`**

Create `tests/unit/test_role_distributor.py`:

```python
"""Tests for role_distributor business logic module."""

from __future__ import annotations

import pytest

from role_distributor import MachineConfig, ParsedConfig, UnitConfig, parse_config


class TestMachineConfig:
    def test_creation(self):
        mc = MachineConfig(
            roles=("control", "storage"),
            workload_params={"microceph": {"flavors": ["rgw"]}},
        )
        assert mc.roles == ("control", "storage")
        assert mc.workload_params == {"microceph": {"flavors": ["rgw"]}}

    def test_frozen(self):
        mc = MachineConfig(roles=("control",), workload_params={})
        with pytest.raises(AttributeError):
            mc.roles = ("storage",)  # type: ignore[misc]


class TestUnitConfig:
    def test_creation(self):
        uc = UnitConfig(roles=("gateway",), workload_params={"flavors": ["rgw"]})
        assert uc.roles == ("gateway",)
        assert uc.workload_params == {"flavors": ["rgw"]}

    def test_frozen(self):
        uc = UnitConfig(roles=("control",), workload_params={})
        with pytest.raises(AttributeError):
            uc.roles = ("storage",)  # type: ignore[misc]


class TestParsedConfig:
    def test_creation(self):
        pc = ParsedConfig(
            machines={"0": MachineConfig(roles=("control",), workload_params={})},
            units={"microceph/0": UnitConfig(roles=("gateway",), workload_params={})},
        )
        assert "0" in pc.machines
        assert "microceph/0" in pc.units


class TestParseConfig:
    def test_machines_only(self):
        yaml_str = """
machines:
  "0":
    roles: [control, storage]
"""
        result = parse_config(yaml_str)
        assert "0" in result.machines
        assert result.machines["0"].roles == ("control", "storage")
        assert result.machines["0"].workload_params == {}
        assert result.units == {}

    def test_units_only(self):
        yaml_str = """
units:
  microceph/0:
    roles: [control, gateway]
"""
        result = parse_config(yaml_str)
        assert result.machines == {}
        assert "microceph/0" in result.units
        assert result.units["microceph/0"].roles == ("control", "gateway")

    def test_both_machines_and_units(self):
        yaml_str = """
machines:
  "0":
    roles: [control, storage]
units:
  microceph/0:
    roles: [gateway]
"""
        result = parse_config(yaml_str)
        assert "0" in result.machines
        assert "microceph/0" in result.units

    def test_machine_with_workload_params(self):
        yaml_str = """
machines:
  "0":
    roles: [control]
    workload-params:
      microceph:
        flavors: [rgw]
      microovn:
        some-key: some-value
"""
        result = parse_config(yaml_str)
        mc = result.machines["0"]
        assert mc.workload_params == {
            "microceph": {"flavors": ["rgw"]},
            "microovn": {"some-key": "some-value"},
        }

    def test_unit_with_workload_params(self):
        yaml_str = """
units:
  microceph/0:
    roles: [gateway]
    workload-params:
      flavors: [rgw, s3]
"""
        result = parse_config(yaml_str)
        uc = result.units["microceph/0"]
        assert uc.workload_params == {"flavors": ["rgw", "s3"]}

    def test_empty_string_raises(self):
        with pytest.raises(ValueError, match="empty"):
            parse_config("")

    def test_malformed_yaml_raises(self):
        with pytest.raises(ValueError):
            parse_config("{{not: valid: yaml")

    def test_neither_machines_nor_units_raises(self):
        with pytest.raises(ValueError, match="machines.*units"):
            parse_config("other-key: value")

    def test_unknown_top_level_keys_raises(self):
        with pytest.raises(ValueError, match="unknown"):
            parse_config("machines:\n  '0':\n    roles: [x]\nunknown-key: 1")

    def test_roles_not_a_list_raises(self):
        with pytest.raises(ValueError, match="roles"):
            parse_config("machines:\n  '0':\n    roles: not-a-list")

    def test_roles_missing_raises(self):
        with pytest.raises(ValueError, match="roles"):
            parse_config("machines:\n  '0':\n    workload-params: {}")

    def test_machines_value_not_a_dict_raises(self):
        with pytest.raises(ValueError):
            parse_config("machines: not-a-dict")

    def test_units_value_not_a_dict_raises(self):
        with pytest.raises(ValueError):
            parse_config("units: not-a-dict")

    def test_yaml_not_a_dict_raises(self):
        with pytest.raises(ValueError):
            parse_config("- a list\n- not a dict")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `PYTHONPATH=src:lib uv run pytest tests/unit/test_role_distributor.py -v`
Expected: ImportError — `MachineConfig`, `ParsedConfig`, etc. do not exist yet.

- [ ] **Step 3: Implement data classes and `parse_config` in `src/role_distributor.py`**

Replace the entire file with:

```python
# Copyright 2026 guillaume.boutry@canonical.com
# See LICENSE file for licensing details.

"""Business logic for role-distributor config parsing and resolution.

This module is independent of the charm framework. It parses the operator's
YAML config blob into typed structures and resolves per-unit assignments
following the precedence rules from the interface spec.
"""

from __future__ import annotations

import dataclasses
from typing import Any

import yaml


@dataclasses.dataclass(frozen=True)
class MachineConfig:
    """Machine-level role configuration.

    Attributes:
        roles: Roles assigned to all units on this machine (unless overridden).
        workload_params: Keyed by application name, since multiple apps share
            a machine. Each value is a dict of params for that app's units.
    """

    roles: tuple[str, ...]
    workload_params: dict[str, dict[str, Any]]


@dataclasses.dataclass(frozen=True)
class UnitConfig:
    """Unit-level role configuration.

    Attributes:
        roles: Roles for this specific unit. Fully replaces machine-level roles.
        workload_params: Params for this unit. Shallow-merges with machine-level.
    """

    roles: tuple[str, ...]
    workload_params: dict[str, Any]


@dataclasses.dataclass(frozen=True)
class ParsedConfig:
    """Parsed role-mapping configuration.

    Attributes:
        machines: Machine ID -> config mapping.
        units: Unit name -> config mapping.
    """

    machines: dict[str, MachineConfig]
    units: dict[str, UnitConfig]


_VALID_TOP_LEVEL_KEYS = frozenset({"machines", "units"})


def _parse_machine_entry(machine_id: str, raw: Any) -> MachineConfig:
    """Parse a single machine config entry."""
    if not isinstance(raw, dict):
        raise ValueError(f"machines['{machine_id}'] must be a dict, got {type(raw).__name__}")
    if "roles" not in raw:
        raise ValueError(f"machines['{machine_id}'] is missing required key 'roles'")
    roles_raw = raw["roles"]
    if not isinstance(roles_raw, list):
        raise ValueError(
            f"machines['{machine_id}'].roles must be a list, got {type(roles_raw).__name__}"
        )
    wp_raw = raw.get("workload-params", {})
    if not isinstance(wp_raw, dict):
        raise ValueError(
            f"machines['{machine_id}'].workload-params must be a dict, "
            f"got {type(wp_raw).__name__}"
        )
    workload_params: dict[str, dict[str, Any]] = {}
    for k, v in wp_raw.items():
        if not isinstance(v, dict):
            raise ValueError(
                f"machines['{machine_id}'].workload-params['{k}'] must be a dict, "
                f"got {type(v).__name__}"
            )
        workload_params[str(k)] = dict(v)
    return MachineConfig(
        roles=tuple(str(r) for r in roles_raw),
        workload_params=workload_params,
    )


def _parse_unit_entry(unit_name: str, raw: Any) -> UnitConfig:
    """Parse a single unit config entry."""
    if not isinstance(raw, dict):
        raise ValueError(f"units['{unit_name}'] must be a dict, got {type(raw).__name__}")
    if "roles" not in raw:
        raise ValueError(f"units['{unit_name}'] is missing required key 'roles'")
    roles_raw = raw["roles"]
    if not isinstance(roles_raw, list):
        raise ValueError(
            f"units['{unit_name}'].roles must be a list, got {type(roles_raw).__name__}"
        )
    wp_raw = raw.get("workload-params", {})
    if not isinstance(wp_raw, dict):
        raise ValueError(
            f"units['{unit_name}'].workload-params must be a dict, "
            f"got {type(wp_raw).__name__}"
        )
    return UnitConfig(
        roles=tuple(str(r) for r in roles_raw),
        workload_params=dict(wp_raw),
    )


def parse_config(yaml_string: str) -> ParsedConfig:
    """Parse a role-mapping YAML config string into a ParsedConfig.

    Args:
        yaml_string: The YAML string from the charm's role-mapping config option.

    Returns:
        A ParsedConfig with parsed machine and unit entries.

    Raises:
        ValueError: If the input is empty, malformed, or has invalid structure.
    """
    if not yaml_string or not yaml_string.strip():
        raise ValueError("role-mapping config is empty")
    try:
        raw = yaml.safe_load(yaml_string)
    except yaml.YAMLError as e:
        raise ValueError(f"role-mapping config is not valid YAML: {e}") from e
    if not isinstance(raw, dict):
        raise ValueError(f"role-mapping config must be a YAML dict, got {type(raw).__name__}")

    unknown_keys = set(raw.keys()) - _VALID_TOP_LEVEL_KEYS
    if unknown_keys:
        raise ValueError(f"role-mapping config has unknown top-level keys: {unknown_keys}")

    has_machines = "machines" in raw
    has_units = "units" in raw
    if not has_machines and not has_units:
        raise ValueError("role-mapping config must have at least one of 'machines' or 'units'")

    machines: dict[str, MachineConfig] = {}
    if has_machines:
        machines_raw = raw["machines"]
        if not isinstance(machines_raw, dict):
            raise ValueError(
                f"'machines' must be a dict, got {type(machines_raw).__name__}"
            )
        for mid, entry in machines_raw.items():
            machines[str(mid)] = _parse_machine_entry(str(mid), entry)

    units: dict[str, UnitConfig] = {}
    if has_units:
        units_raw = raw["units"]
        if not isinstance(units_raw, dict):
            raise ValueError(f"'units' must be a dict, got {type(units_raw).__name__}")
        for uname, entry in units_raw.items():
            units[str(uname)] = _parse_unit_entry(str(uname), entry)

    return ParsedConfig(machines=machines, units=units)
```

Note: `compute_assignments` is not here yet — that is Task 3.

- [ ] **Step 4: Run tests to verify they pass**

Run: `PYTHONPATH=src:lib uv run pytest tests/unit/test_role_distributor.py -v`
Expected: All 19 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/role_distributor.py tests/unit/test_role_distributor.py
git commit -m "feat: implement parse_config with data classes and validation"
```

---

### Task 3: Business Logic — `compute_assignments`

**Files:**
- Modify: `tests/unit/test_role_distributor.py`
- Modify: `src/role_distributor.py`

**Context:** `compute_assignments` takes a `ParsedConfig` and a list of `RegisteredUnit` objects (from the library at `lib/charms/role_distributor/v0/role_assignment.py`). It resolves roles and workload-params per the precedence rules:
1. Unit-level roles fully replace machine-level roles.
2. Workload-params: machine-level (scoped by app name) is the base, unit-level overrides individual keys.
3. Units without `machine_id` only get unit-level config.

It returns `dict[str, UnitRoleAssignment]` — entries for every registered unit, with unmatched units getting `status="pending"`.

- [ ] **Step 1: Write failing tests for `compute_assignments`**

Append to `tests/unit/test_role_distributor.py`:

```python
from charms.role_distributor.v0.role_assignment import (
    RegisteredUnit,
    UnitRoleAssignment,
)

from role_distributor import compute_assignments


class TestComputeAssignments:
    def test_unit_level_match(self):
        """Unit with matching unit-level config gets assigned."""
        config = ParsedConfig(
            machines={},
            units={
                "microceph/0": UnitConfig(
                    roles=("control", "storage"), workload_params={}
                ),
            },
        )
        units = [
            RegisteredUnit(
                unit_name="microceph/0",
                model_name="ceph-model",
                application_name="microceph",
            ),
        ]
        result = compute_assignments(config, units)
        assert result["microceph/0"] == UnitRoleAssignment(
            status="assigned", roles=("control", "storage")
        )

    def test_machine_level_match(self):
        """Unit with machine-id gets roles from machine-level config."""
        config = ParsedConfig(
            machines={
                "0": MachineConfig(roles=("control", "storage"), workload_params={}),
            },
            units={},
        )
        units = [
            RegisteredUnit(
                unit_name="microceph/0",
                model_name="ceph-model",
                application_name="microceph",
                machine_id="0",
            ),
        ]
        result = compute_assignments(config, units)
        assert result["microceph/0"] == UnitRoleAssignment(
            status="assigned", roles=("control", "storage")
        )

    def test_unit_level_roles_override_machine_level(self):
        """Unit-level roles fully replace machine-level roles."""
        config = ParsedConfig(
            machines={
                "0": MachineConfig(roles=("control", "storage"), workload_params={}),
            },
            units={
                "microceph/0": UnitConfig(roles=("gateway",), workload_params={}),
            },
        )
        units = [
            RegisteredUnit(
                unit_name="microceph/0",
                model_name="ceph-model",
                application_name="microceph",
                machine_id="0",
            ),
        ]
        result = compute_assignments(config, units)
        assert result["microceph/0"].roles == ("gateway",)

    def test_workload_params_shallow_merge(self):
        """Machine-level params are base, unit-level overrides individual keys."""
        config = ParsedConfig(
            machines={
                "0": MachineConfig(
                    roles=("control",),
                    workload_params={
                        "microceph": {"flavors": ["rgw"], "region": "us-east"},
                    },
                ),
            },
            units={
                "microceph/0": UnitConfig(
                    roles=("gateway",),
                    workload_params={"flavors": ["rgw", "s3"]},
                ),
            },
        )
        units = [
            RegisteredUnit(
                unit_name="microceph/0",
                model_name="ceph-model",
                application_name="microceph",
                machine_id="0",
            ),
        ]
        result = compute_assignments(config, units)
        assert result["microceph/0"].workload_params == {
            "flavors": ["rgw", "s3"],  # unit overrides
            "region": "us-east",  # machine preserved
        }

    def test_workload_params_none_when_empty(self):
        """workload_params is None when resolved dict is empty."""
        config = ParsedConfig(
            machines={},
            units={
                "microceph/0": UnitConfig(roles=("control",), workload_params={}),
            },
        )
        units = [
            RegisteredUnit(
                unit_name="microceph/0",
                model_name="ceph-model",
                application_name="microceph",
            ),
        ]
        result = compute_assignments(config, units)
        assert result["microceph/0"].workload_params is None

    def test_machine_workload_params_scoped_by_app_name(self):
        """Machine-level workload-params are scoped by application name."""
        config = ParsedConfig(
            machines={
                "0": MachineConfig(
                    roles=("control",),
                    workload_params={
                        "microceph": {"flavors": ["rgw"]},
                        "microovn": {"some-key": "some-value"},
                    },
                ),
            },
            units={},
        )
        ceph_unit = RegisteredUnit(
            unit_name="microceph/0",
            model_name="ceph-model",
            application_name="microceph",
            machine_id="0",
        )
        ovn_unit = RegisteredUnit(
            unit_name="microovn/0",
            model_name="ovn-model",
            application_name="microovn",
            machine_id="0",
        )
        result = compute_assignments(config, [ceph_unit, ovn_unit])
        assert result["microceph/0"].workload_params == {"flavors": ["rgw"]}
        assert result["microovn/0"].workload_params == {"some-key": "some-value"}

    def test_unit_without_machine_id_skips_machine_config(self):
        """Unit without machine-id only gets unit-level config."""
        config = ParsedConfig(
            machines={
                "0": MachineConfig(roles=("control",), workload_params={}),
            },
            units={},
        )
        units = [
            RegisteredUnit(
                unit_name="microceph/0",
                model_name="ceph-model",
                application_name="microceph",
                machine_id=None,
            ),
        ]
        result = compute_assignments(config, units)
        assert result["microceph/0"] == UnitRoleAssignment(status="pending")

    def test_no_match_returns_pending(self):
        """Unit with no matching config gets pending status."""
        config = ParsedConfig(machines={}, units={})
        units = [
            RegisteredUnit(
                unit_name="microceph/0",
                model_name="ceph-model",
                application_name="microceph",
            ),
        ]
        result = compute_assignments(config, units)
        assert result["microceph/0"] == UnitRoleAssignment(status="pending")

    def test_multiple_units_mixed(self):
        """Multiple units with different match states."""
        config = ParsedConfig(
            machines={},
            units={
                "microceph/0": UnitConfig(roles=("control",), workload_params={}),
            },
        )
        units = [
            RegisteredUnit(
                unit_name="microceph/0",
                model_name="m",
                application_name="microceph",
            ),
            RegisteredUnit(
                unit_name="microceph/1",
                model_name="m",
                application_name="microceph",
            ),
        ]
        result = compute_assignments(config, units)
        assert result["microceph/0"].status == "assigned"
        assert result["microceph/1"].status == "pending"

    def test_machine_only_workload_params_for_app(self):
        """Machine-level workload-params applied when no unit-level params exist."""
        config = ParsedConfig(
            machines={
                "0": MachineConfig(
                    roles=("control",),
                    workload_params={"microceph": {"flavors": ["rgw"]}},
                ),
            },
            units={},
        )
        units = [
            RegisteredUnit(
                unit_name="microceph/0",
                model_name="ceph-model",
                application_name="microceph",
                machine_id="0",
            ),
        ]
        result = compute_assignments(config, units)
        assert result["microceph/0"].workload_params == {"flavors": ["rgw"]}

    def test_machine_workload_params_missing_app_entry(self):
        """Machine has workload-params but not for this unit's application."""
        config = ParsedConfig(
            machines={
                "0": MachineConfig(
                    roles=("control",),
                    workload_params={"microovn": {"key": "val"}},
                ),
            },
            units={},
        )
        units = [
            RegisteredUnit(
                unit_name="microceph/0",
                model_name="ceph-model",
                application_name="microceph",
                machine_id="0",
            ),
        ]
        result = compute_assignments(config, units)
        assert result["microceph/0"].workload_params is None
        assert result["microceph/0"].roles == ("control",)
```

- [ ] **Step 2: Run tests to verify the new ones fail**

Run: `PYTHONPATH=src:lib uv run pytest tests/unit/test_role_distributor.py::TestComputeAssignments -v`
Expected: ImportError — `compute_assignments` does not exist yet.

- [ ] **Step 3: Implement `compute_assignments` in `src/role_distributor.py`**

Add this function at the bottom of the file, plus the import of `RegisteredUnit` and `UnitRoleAssignment`:

```python
from charms.role_distributor.v0.role_assignment import (
    RegisteredUnit,
    UnitRoleAssignment,
)


def compute_assignments(
    config: ParsedConfig,
    registered_units: list[RegisteredUnit],
) -> dict[str, UnitRoleAssignment]:
    """Resolve per-unit role assignments from config and registered units.

    Resolution precedence (from interface spec):
    1. Roles: unit-level fully replaces machine-level. No merging.
    2. workload-params: shallow merge. Machine-level (scoped by app name) is the
       base, unit-level overrides individual keys.
    3. Units without machine_id only receive unit-level config.

    Args:
        config: Parsed role-mapping configuration.
        registered_units: Units registered via the role-assignment relation.

    Returns:
        Dict mapping unit names to their resolved assignments. Every unit in
        registered_units gets an entry; unmatched units get status="pending".
    """
    assignments: dict[str, UnitRoleAssignment] = {}
    for unit in registered_units:
        unit_cfg = config.units.get(unit.unit_name)
        machine_cfg = (
            config.machines.get(unit.machine_id)
            if unit.machine_id is not None
            else None
        )

        # Resolve roles: unit-level wins, then machine-level, then no match.
        if unit_cfg is not None:
            roles = unit_cfg.roles
        elif machine_cfg is not None:
            roles = machine_cfg.roles
        else:
            assignments[unit.unit_name] = UnitRoleAssignment(status="pending")
            continue

        # Resolve workload-params: machine base (scoped by app), unit overrides.
        resolved_params: dict[str, Any] = {}
        if machine_cfg is not None:
            resolved_params.update(
                machine_cfg.workload_params.get(unit.application_name, {})
            )
        if unit_cfg is not None:
            resolved_params.update(unit_cfg.workload_params)

        assignments[unit.unit_name] = UnitRoleAssignment(
            status="assigned",
            roles=roles,
            workload_params=resolved_params or None,
        )
    return assignments
```

Note: this requires adding `from typing import Any` if not already present (it is already imported via `from typing import Any` in the dataclasses section).

- [ ] **Step 4: Run all tests to verify they pass**

Run: `PYTHONPATH=src:lib uv run pytest tests/unit/test_role_distributor.py -v`
Expected: All tests PASS (both `parse_config` tests from Task 2 and `compute_assignments` tests).

- [ ] **Step 5: Commit**

```bash
git add src/role_distributor.py tests/unit/test_role_distributor.py
git commit -m "feat: implement compute_assignments with resolution precedence"
```

---

### Task 4: Charm Implementation

**Files:**
- Rewrite: `tests/unit/test_charm.py`
- Rewrite: `src/charm.py`

**Context:** The charm instantiates `RoleAssignmentProvider` from the library, observes raw relation events + `config-changed` + `leader-elected`, and funnels everything through `_reconcile()`. The reconcile method reads config, calls `parse_config` + `compute_assignments`, and publishes assignments on each relation. Non-leaders return early (only leader can write app databag).

The library `RoleAssignmentProvider` is at `lib/charms/role_distributor/v0/role_assignment.py`. It provides `get_registered_units(relation)` and `set_assignments(relation, dict)`. The charm must also declare the relation metadata in its test META dict to match `charmcraft.yaml`.

- [ ] **Step 1: Write failing tests for the charm**

Replace `tests/unit/test_charm.py` entirely with:

```python
"""Unit tests for role-distributor charm."""

from __future__ import annotations

import json

import ops
import ops.testing

from charm import RoleDistributorCharm

CHARM_META = {
    "name": "role-distributor",
    "provides": {"role-assignment": {"interface": "role-assignment"}},
}

CHARM_CONFIG = {
    "options": {
        "role-mapping": {
            "type": "string",
            "default": "",
            "description": "YAML blob defining role assignments.",
        },
    },
}

CONFIG_MACHINES_ONLY = """
machines:
  "0":
    roles: [control, storage]
"""

CONFIG_UNITS_ONLY = """
units:
  microceph/0:
    roles: [control, gateway]
    workload-params:
      flavors: [rgw]
"""

CONFIG_MIXED = """
machines:
  "0":
    roles: [control, storage]
    workload-params:
      microceph:
        region: us-east
units:
  microceph/0:
    roles: [gateway]
    workload-params:
      flavors: [rgw, s3]
"""


def _make_relation(
    remote_app_data: dict | None = None,
    remote_units_data: dict | None = None,
) -> ops.testing.Relation:
    """Create a role-assignment relation with optional remote data."""
    return ops.testing.Relation(
        endpoint="role-assignment",
        interface="role-assignment",
        remote_app_data=remote_app_data or {},
        remote_units_data=remote_units_data or {},
    )


class TestReconcileNoRelation:
    def test_no_config_sets_blocked(self):
        """No role-mapping config -> BlockedStatus."""
        ctx = ops.testing.Context(
            RoleDistributorCharm, meta=CHARM_META, charm_config=CHARM_CONFIG
        )
        state = ops.testing.State(leader=True)
        out = ctx.run(ctx.on.config_changed(), state)
        assert out.unit_status == ops.testing.BlockedStatus(
            "no role-mapping config provided"
        )

    def test_invalid_yaml_sets_blocked(self):
        """Invalid YAML in role-mapping -> BlockedStatus with error."""
        ctx = ops.testing.Context(
            RoleDistributorCharm,
            meta=CHARM_META,
            charm_config=CHARM_CONFIG,
            config={"role-mapping": "{{invalid yaml"},
        )
        state = ops.testing.State(leader=True)
        out = ctx.run(ctx.on.config_changed(), state)
        assert isinstance(out.unit_status, ops.testing.BlockedStatus)
        assert "invalid role-mapping config" in out.unit_status.message

    def test_valid_config_no_relations_sets_active(self):
        """Valid config but no relations -> ActiveStatus (no pending units)."""
        ctx = ops.testing.Context(
            RoleDistributorCharm,
            meta=CHARM_META,
            charm_config=CHARM_CONFIG,
            config={"role-mapping": CONFIG_UNITS_ONLY},
        )
        state = ops.testing.State(leader=True)
        out = ctx.run(ctx.on.config_changed(), state)
        assert out.unit_status == ops.testing.ActiveStatus()


class TestReconcileWithRelation:
    def test_matched_units_sets_active(self):
        """All units matched -> ActiveStatus + correct assignments in databag."""
        relation = _make_relation(
            remote_app_data={
                "model-name": "ceph-model",
                "application-name": "microceph",
            },
            remote_units_data={
                0: {"unit-name": "microceph/0"},
            },
        )
        ctx = ops.testing.Context(
            RoleDistributorCharm,
            meta=CHARM_META,
            charm_config=CHARM_CONFIG,
            config={"role-mapping": CONFIG_UNITS_ONLY},
        )
        state = ops.testing.State(relations=[relation], leader=True)
        out = ctx.run(ctx.on.config_changed(), state)
        assert out.unit_status == ops.testing.ActiveStatus()

        out_rel = out.get_relation(relation.id)
        raw = out_rel.local_app_data.get("assignments")
        assert raw is not None
        parsed = json.loads(raw)
        assert parsed["microceph/0"]["status"] == "assigned"
        assert parsed["microceph/0"]["roles"] == ["control", "gateway"]
        assert parsed["microceph/0"]["workload-params"] == {"flavors": ["rgw"]}

    def test_unmatched_units_sets_waiting(self):
        """Some units not in config -> WaitingStatus with count."""
        relation = _make_relation(
            remote_app_data={
                "model-name": "ceph-model",
                "application-name": "microceph",
            },
            remote_units_data={
                0: {"unit-name": "microceph/0"},
                1: {"unit-name": "microceph/1"},
            },
        )
        ctx = ops.testing.Context(
            RoleDistributorCharm,
            meta=CHARM_META,
            charm_config=CHARM_CONFIG,
            config={"role-mapping": CONFIG_UNITS_ONLY},
        )
        state = ops.testing.State(relations=[relation], leader=True)
        out = ctx.run(ctx.on.config_changed(), state)
        assert isinstance(out.unit_status, ops.testing.WaitingStatus)
        assert "1" in out.unit_status.message

    def test_machine_level_assignment(self):
        """Unit with machine-id matched via machine-level config."""
        relation = _make_relation(
            remote_app_data={
                "model-name": "ceph-model",
                "application-name": "microceph",
            },
            remote_units_data={
                0: {"unit-name": "microceph/0", "machine-id": "0"},
            },
        )
        ctx = ops.testing.Context(
            RoleDistributorCharm,
            meta=CHARM_META,
            charm_config=CHARM_CONFIG,
            config={"role-mapping": CONFIG_MACHINES_ONLY},
        )
        state = ops.testing.State(relations=[relation], leader=True)
        out = ctx.run(ctx.on.config_changed(), state)
        assert out.unit_status == ops.testing.ActiveStatus()

        out_rel = out.get_relation(relation.id)
        parsed = json.loads(out_rel.local_app_data["assignments"])
        assert parsed["microceph/0"]["status"] == "assigned"
        assert parsed["microceph/0"]["roles"] == ["control", "storage"]

    def test_mixed_resolution_precedence(self):
        """Unit-level roles override machine-level, workload-params shallow-merge."""
        relation = _make_relation(
            remote_app_data={
                "model-name": "ceph-model",
                "application-name": "microceph",
            },
            remote_units_data={
                0: {"unit-name": "microceph/0", "machine-id": "0"},
            },
        )
        ctx = ops.testing.Context(
            RoleDistributorCharm,
            meta=CHARM_META,
            charm_config=CHARM_CONFIG,
            config={"role-mapping": CONFIG_MIXED},
        )
        state = ops.testing.State(relations=[relation], leader=True)
        out = ctx.run(ctx.on.config_changed(), state)

        out_rel = out.get_relation(relation.id)
        parsed = json.loads(out_rel.local_app_data["assignments"])
        entry = parsed["microceph/0"]
        assert entry["roles"] == ["gateway"]  # unit-level overrides
        assert entry["workload-params"]["flavors"] == ["rgw", "s3"]  # unit overrides
        assert entry["workload-params"]["region"] == "us-east"  # machine preserved


class TestReconcileNonLeader:
    def test_non_leader_does_not_write(self):
        """Non-leader does not write to app databag."""
        relation = _make_relation(
            remote_app_data={
                "model-name": "ceph-model",
                "application-name": "microceph",
            },
            remote_units_data={
                0: {"unit-name": "microceph/0"},
            },
        )
        ctx = ops.testing.Context(
            RoleDistributorCharm,
            meta=CHARM_META,
            charm_config=CHARM_CONFIG,
            config={"role-mapping": CONFIG_UNITS_ONLY},
        )
        state = ops.testing.State(relations=[relation], leader=False)
        out = ctx.run(ctx.on.config_changed(), state)
        out_rel = out.get_relation(relation.id)
        assert "assignments" not in out_rel.local_app_data
        assert out.unit_status == ops.testing.ActiveStatus()


class TestReconcileTriggers:
    def test_relation_changed_triggers_reconcile(self):
        """relation-changed on role-assignment triggers reconcile."""
        relation = _make_relation(
            remote_app_data={
                "model-name": "ceph-model",
                "application-name": "microceph",
            },
            remote_units_data={
                0: {"unit-name": "microceph/0"},
            },
        )
        ctx = ops.testing.Context(
            RoleDistributorCharm,
            meta=CHARM_META,
            charm_config=CHARM_CONFIG,
            config={"role-mapping": CONFIG_UNITS_ONLY},
        )
        state = ops.testing.State(relations=[relation], leader=True)
        out = ctx.run(ctx.on.relation_changed(relation), state)
        assert out.unit_status == ops.testing.ActiveStatus()
        out_rel = out.get_relation(relation.id)
        assert "assignments" in out_rel.local_app_data

    def test_relation_departed_triggers_reconcile(self):
        """relation-departed triggers reconcile."""
        relation = _make_relation(
            remote_app_data={
                "model-name": "ceph-model",
                "application-name": "microceph",
            },
            remote_units_data={
                0: {"unit-name": "microceph/0"},
            },
        )
        ctx = ops.testing.Context(
            RoleDistributorCharm,
            meta=CHARM_META,
            charm_config=CHARM_CONFIG,
            config={"role-mapping": CONFIG_UNITS_ONLY},
        )
        state = ops.testing.State(relations=[relation], leader=True)
        out = ctx.run(ctx.on.relation_departed(relation, remote_unit=0), state)
        assert "assignments" in out.get_relation(relation.id).local_app_data

    def test_leader_elected_triggers_reconcile(self):
        """leader-elected triggers reconcile."""
        relation = _make_relation(
            remote_app_data={
                "model-name": "ceph-model",
                "application-name": "microceph",
            },
            remote_units_data={
                0: {"unit-name": "microceph/0"},
            },
        )
        ctx = ops.testing.Context(
            RoleDistributorCharm,
            meta=CHARM_META,
            charm_config=CHARM_CONFIG,
            config={"role-mapping": CONFIG_UNITS_ONLY},
        )
        state = ops.testing.State(relations=[relation], leader=True)
        out = ctx.run(ctx.on.leader_elected(), state)
        assert out.unit_status == ops.testing.ActiveStatus()
        out_rel = out.get_relation(relation.id)
        assert "assignments" in out_rel.local_app_data
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `PYTHONPATH=src:lib uv run pytest tests/unit/test_charm.py -v`
Expected: Failures — the charm doesn't have reconcile logic yet.

- [ ] **Step 3: Implement the charm in `src/charm.py`**

Replace the entire file with:

```python
#!/usr/bin/env python3
# Copyright 2026 guillaume.boutry@canonical.com
# See LICENSE file for licensing details.

"""Role Distributor charm."""

from __future__ import annotations

import logging

import ops

import role_distributor
from charms.role_distributor.v0.role_assignment import RoleAssignmentProvider

logger = logging.getLogger(__name__)


class RoleDistributorCharm(ops.CharmBase):
    """Charm that distributes roles to related applications.

    The operator provides a YAML config blob with machine-level and unit-level
    role mappings. The charm resolves and publishes per-unit assignments to all
    related applications through the role-assignment interface.
    """

    def __init__(self, framework: ops.Framework):
        super().__init__(framework)
        self._provider = RoleAssignmentProvider(self, "role-assignment")
        framework.observe(self.on.config_changed, self._reconcile)
        framework.observe(
            self.on["role-assignment"].relation_changed, self._reconcile
        )
        framework.observe(
            self.on["role-assignment"].relation_departed, self._reconcile
        )
        framework.observe(self.on.leader_elected, self._reconcile)

    def _reconcile(self, _event: ops.EventBase) -> None:
        """Re-evaluate and publish role assignments on all relations."""
        if not self.unit.is_leader():
            self.unit.status = ops.ActiveStatus()
            return

        raw_config = str(self.config.get("role-mapping", ""))
        if not raw_config.strip():
            self.unit.status = ops.BlockedStatus(
                "no role-mapping config provided"
            )
            return

        try:
            parsed = role_distributor.parse_config(raw_config)
        except ValueError as e:
            self.unit.status = ops.BlockedStatus(
                f"invalid role-mapping config: {e}"
            )
            return

        total_pending = 0
        for relation in self.model.relations.get("role-assignment", []):
            registered = self._provider.get_registered_units(relation)
            assignments = role_distributor.compute_assignments(
                parsed, registered
            )
            self._provider.set_assignments(relation, assignments)
            total_pending += sum(
                1 for a in assignments.values() if a.status == "pending"
            )

        if total_pending > 0:
            self.unit.status = ops.WaitingStatus(
                f"units awaiting assignment: {total_pending}"
            )
        else:
            self.unit.status = ops.ActiveStatus()


if __name__ == "__main__":  # pragma: nocover
    ops.main(RoleDistributorCharm)
```

- [ ] **Step 4: Run all unit tests**

Run: `PYTHONPATH=src:lib uv run pytest tests/unit/ -v`
Expected: All tests PASS (charm tests + role_distributor tests + library tests).

- [ ] **Step 5: Run coverage check**

Run: `PYTHONPATH=src:lib uv run coverage run --source=src -m pytest tests/unit/ && uv run coverage report`
Expected: Coverage >= 80% for `src/`.

- [ ] **Step 6: Commit**

```bash
git add src/charm.py tests/unit/test_charm.py
git commit -m "feat: implement charm with reconcile loop and status management"
```

---

### Task 5: Integration Tests (Jubilant)

**Files:**
- Create: `tests/integration/conftest.py`
- Rewrite: `tests/integration/test_charm.py`

**Context:** Jubilant is a synchronous Juju CLI wrapper (`>=1.0`). It replaces `pytest-operator` and `python-libjuju`. All calls are synchronous — no `async`/`await`. `jubilant.temp_model()` creates and destroys models automatically. `juju.wait(jubilant.all_active)` blocks until all units are active/idle.

Integration tests are run via `tox -e integration` and require a pre-packed `.charm` file and a bootstrapped Juju controller (typically via Concierge in CI).

- [ ] **Step 1: Create `tests/integration/conftest.py`**

```python
"""Integration test fixtures for role-distributor charm."""

import logging
import os
import pathlib
import sys
import time

import jubilant
import pytest

logger = logging.getLogger(__name__)


@pytest.fixture(scope="module")
def juju(request: pytest.FixtureRequest):
    """Create a temporary Juju model for running tests."""
    with jubilant.temp_model() as juju:
        yield juju
        if request.session.testsfailed:
            logger.info("Collecting Juju logs...")
            time.sleep(0.5)
            log = juju.debug_log(limit=1000)
            print(log, end="", file=sys.stderr)


@pytest.fixture(scope="session")
def charm():
    """Return the path of the .charm file under test."""
    if "CHARM_PATH" in os.environ:
        charm_path = pathlib.Path(os.environ["CHARM_PATH"])
        if not charm_path.exists():
            raise FileNotFoundError(f"Charm does not exist: {charm_path}")
        return charm_path
    return next(pathlib.Path(".").glob("*.charm"))
```

- [ ] **Step 2: Rewrite `tests/integration/test_charm.py`**

Replace the entire file with:

```python
"""Integration tests for role-distributor charm."""

from __future__ import annotations

import pathlib

import jubilant


def test_deploy_blocked_without_config(
    charm: pathlib.Path, juju: jubilant.Juju
):
    """Deploy the charm. Without config it should reach blocked status."""
    juju.deploy(f"./{charm}")
    juju.wait(lambda status: jubilant.all_blocked(status, "role-distributor"))


def test_config_sets_active(juju: jubilant.Juju):
    """Setting a valid role-mapping config transitions to active."""
    config = """
units:
  role-distributor/0:
    roles: [control]
"""
    juju.config("role-distributor", {"role-mapping": config})
    juju.wait(jubilant.all_active)
```

- [ ] **Step 3: Commit**

```bash
git add tests/integration/conftest.py tests/integration/test_charm.py
git commit -m "test: add jubilant integration tests"
```

---

### Task 6: CI Workflows

**Files:**
- Create: `.github/workflows/ci.yaml`
- Create: `.github/workflows/integration.yaml`
- Create: `.github/workflows/release.yaml`

- [ ] **Step 1: Create `.github/workflows/ci.yaml`**

```yaml
name: CI

on:
  push:
    branches: [main]
  pull_request:

jobs:
  lint:
    runs-on: ubuntu-24.04
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
      - run: uv tool install tox --with tox-uv
      - run: tox -e lint

  unit:
    runs-on: ubuntu-24.04
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
      - run: uv tool install tox --with tox-uv
      - run: tox -e unit
      - uses: actions/upload-artifact@v4
        if: always()
        with:
          name: coverage-report
          path: .coverage
```

- [ ] **Step 2: Create `.github/workflows/integration.yaml`**

```yaml
name: Integration Tests

on:
  workflow_dispatch:
  schedule:
    - cron: "0 3 * * *"  # nightly at 03:00 UTC

jobs:
  integration:
    runs-on: ubuntu-24.04
    steps:
      - uses: actions/checkout@v4
      - name: Install Concierge
        run: sudo snap install --classic concierge
      - name: Bootstrap Juju + LXD
        run: sudo concierge prepare --preset machine --extra-snaps astral-uv
      - name: Pack charm
        run: charmcraft pack
      - name: Run integration tests
        run: |
          uv tool install tox --with tox-uv
          tox -e integration
```

- [ ] **Step 3: Create `.github/workflows/release.yaml`**

```yaml
name: Release

on:
  push:
    tags: ["v*"]

jobs:
  release:
    runs-on: ubuntu-24.04
    steps:
      - uses: actions/checkout@v4
      - name: Pack charm
        run: charmcraft pack
      - name: Upload and release
        run: |
          CHARM_FILE=$(ls *.charm)
          charmcraft upload "$CHARM_FILE"
          charmcraft release role-distributor --revision=$(charmcraft revisions role-distributor | head -2 | tail -1 | awk '{print $1}') --channel=latest/edge
```

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/ci.yaml .github/workflows/integration.yaml .github/workflows/release.yaml
git commit -m "ci: add lint, unit, integration, and release workflows"
```

---

### Task 7: README and Documentation

**Files:**
- Rewrite: `README.md`

- [ ] **Step 1: Rewrite `README.md`**

Replace the entire file with:

```markdown
# role-distributor

A Juju machine charm that acts as a central role distributor. The operator
provides a YAML mapping of machines and units to roles via config, and the
charm resolves and publishes assignments to all related applications through
the `role-assignment` interface.

## Quick Start

```bash
juju deploy ./role-distributor_*.charm
```

Configure role assignments:

```bash
juju config role-distributor role-mapping="$(cat <<'EOF'
machines:
  "0":
    roles: [control, storage, network]
    workload-params:
      microceph:
        flavors: [rgw]
  "1":
    roles: [storage, network]
units:
  microceph/0:
    roles: [control, storage, gateway]
    workload-params:
      flavors: [rgw, s3]
EOF
)"
```

Integrate with a requirer charm:

```bash
juju integrate role-distributor:role-assignment microceph:role-assignment
```

## Development

```bash
uv sync --group dev --group test
pre-commit install
tox -e lint     # ruff + ty
tox -e unit     # pytest + coverage
tox -e format   # auto-fix
```

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).
```

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: replace placeholder README with charm documentation"
```

---

### Task 8: Final Validation

**Files:** None (validation only).

This task runs through the checklist from PLAN.md to verify everything works.

- [ ] **Step 1: Verify `uv lock` succeeds**

Run: `uv lock`
Expected: No errors.

- [ ] **Step 2: Verify lint passes**

Run: `uv run tox -e lint`
Expected: Clean pass. If there are lint issues in existing library files, fix them.

- [ ] **Step 3: Verify unit tests pass with coverage**

Run: `uv run tox -e unit`
Expected: All tests pass, coverage >= 80%.

- [ ] **Step 4: Verify pre-commit hooks work**

Run: `uv run pre-commit run --all-files`
Expected: All hooks pass. If ruff or ty finds issues, fix them.

- [ ] **Step 5: Verify every relation endpoint in charm.py is in charmcraft.yaml**

Check: `src/charm.py` references `"role-assignment"` endpoint. `charmcraft.yaml` has `provides: role-assignment: interface: role-assignment`. Match confirmed.

- [ ] **Step 6: Verify library is importable from charm**

Run: `PYTHONPATH=lib:src python -c "from charms.role_distributor.v0.role_assignment import RoleAssignmentProvider; print('OK')"`
Expected: `OK`

- [ ] **Step 7: Fix any issues found and commit**

If any validation steps failed, fix the issues and commit:

```bash
git add -A
git commit -m "fix: address validation issues"
```
