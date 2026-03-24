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
from charms.role_distributor.v0.role_assignment import (
    RegisteredUnit,
    UnitRoleAssignment,
)


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
            f"machines['{machine_id}'].workload-params must be a dict, got {type(wp_raw).__name__}"
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
            f"units['{unit_name}'].workload-params must be a dict, got {type(wp_raw).__name__}"
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

    has_machines = "machines" in raw
    has_units = "units" in raw
    if not has_machines and not has_units:
        raise ValueError("role-mapping config must have at least one of 'machines' or 'units'")

    unknown_keys = set(raw.keys()) - _VALID_TOP_LEVEL_KEYS
    if unknown_keys:
        raise ValueError(f"role-mapping config has unknown top-level keys: {unknown_keys}")

    machines: dict[str, MachineConfig] = {}
    if has_machines:
        machines_raw = raw["machines"]
        if not isinstance(machines_raw, dict):
            raise ValueError(f"'machines' must be a dict, got {type(machines_raw).__name__}")
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
        machine_cfg = config.machines.get(unit.machine_id) if unit.machine_id is not None else None

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
            resolved_params.update(machine_cfg.workload_params.get(unit.application_name, {}))
        if unit_cfg is not None:
            resolved_params.update(unit_cfg.workload_params)

        assignments[unit.unit_name] = UnitRoleAssignment(
            status="assigned",
            roles=roles,
            workload_params=resolved_params or None,
        )
    return assignments
