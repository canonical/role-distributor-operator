# Copyright 2026 guillaume.boutry@canonical.com
# See LICENSE file for licensing details.

"""Business logic for role-distributor config parsing and resolution.

This module is independent of the charm framework. It parses the operator's
YAML config blob into typed structures and resolves per-unit assignments
following the precedence rules from the interface spec.

Config format::

    <model-name>:
      <application-name>:
        machines:
          <machine-id>:
            roles: [role1, role2]
            workload-params: {key: value}
        units:
          <unit-name>:
            roles: [role3]
            workload-params: {key: value}
"""

from __future__ import annotations

import dataclasses
import logging
from typing import Any

import yaml
from charms.role_distributor.v0.role_assignment import (
    AssignmentStatus,
    RegisteredUnit,
    UnitRoleAssignment,
)

logger = logging.getLogger(__name__)


@dataclasses.dataclass(frozen=True)
class MachineConfig:
    """Machine-level role configuration.

    Attributes:
        roles: Roles assigned to this application's units on this machine
            (unless overridden).
        workload_params: Default params for this application's units on
            this machine.
    """

    roles: tuple[str, ...]
    workload_params: dict[str, Any]


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
class ApplicationConfig:
    """Per-application role configuration.

    Attributes:
        machines: Machine ID -> config mapping within this application.
        units: Unit name -> config mapping within this application.
    """

    machines: dict[str, MachineConfig]
    units: dict[str, UnitConfig]


@dataclasses.dataclass(frozen=True)
class ModelConfig:
    """Per-model role configuration.

    Attributes:
        applications: Application name -> config mapping within this model.
    """

    applications: dict[str, ApplicationConfig]


@dataclasses.dataclass(frozen=True)
class ParsedConfig:
    """Parsed role-mapping configuration.

    Attributes:
        models: Model name -> config mapping.
    """

    models: dict[str, ModelConfig]


def _parse_machine_entry(model: str, app_name: str, machine_id: str, raw: Any) -> MachineConfig:
    """Parse a single machine config entry."""
    if not isinstance(raw, dict):
        raise ValueError(
            f"{model}['{app_name}'].machines['{machine_id}'] must be a dict, "
            f"got {type(raw).__name__}"
        )
    if "roles" not in raw:
        raise ValueError(
            f"{model}['{app_name}'].machines['{machine_id}'] is missing required key 'roles'"
        )
    roles_raw = raw["roles"]
    if not isinstance(roles_raw, list):
        raise ValueError(
            f"{model}['{app_name}'].machines['{machine_id}'].roles must be a list, "
            f"got {type(roles_raw).__name__}"
        )
    wp_raw = raw.get("workload-params", {})
    if not isinstance(wp_raw, dict):
        raise ValueError(
            f"{model}['{app_name}'].machines['{machine_id}'].workload-params must be a dict, "
            f"got {type(wp_raw).__name__}"
        )
    return MachineConfig(
        roles=tuple(str(r) for r in roles_raw),
        workload_params=dict(wp_raw),
    )


def _parse_unit_entry(model: str, app_name: str, unit_name: str, raw: Any) -> UnitConfig:
    """Parse a single unit config entry."""
    if "/" not in unit_name:
        raise ValueError(f"{model}['{app_name}'].units key '{unit_name}' must be a full unit name")
    if not unit_name.startswith(f"{app_name}/"):
        raise ValueError(
            f"{model}['{app_name}'].units['{unit_name}'] must belong to application '{app_name}'"
        )
    if not isinstance(raw, dict):
        raise ValueError(
            f"{model}['{app_name}'].units['{unit_name}'] must be a dict, got {type(raw).__name__}"
        )
    if "roles" not in raw:
        raise ValueError(
            f"{model}['{app_name}'].units['{unit_name}'] is missing required key 'roles'"
        )
    roles_raw = raw["roles"]
    if not isinstance(roles_raw, list):
        raise ValueError(
            f"{model}['{app_name}'].units['{unit_name}'].roles must be a list, "
            f"got {type(roles_raw).__name__}"
        )
    wp_raw = raw.get("workload-params", {})
    if not isinstance(wp_raw, dict):
        raise ValueError(
            f"{model}['{app_name}'].units['{unit_name}'].workload-params must be a dict, "
            f"got {type(wp_raw).__name__}"
        )
    return UnitConfig(
        roles=tuple(str(r) for r in roles_raw),
        workload_params=dict(wp_raw),
    )


def _parse_application_entry(model: str, app_name: str, raw: Any) -> ApplicationConfig:
    """Parse a single application config entry."""
    if not isinstance(raw, dict):
        raise ValueError(
            f"application '{app_name}' in model '{model}' must be a dict, got {type(raw).__name__}"
        )

    allowed_keys = {"machines", "units"}
    unknown_keys = set(raw) - allowed_keys
    if unknown_keys:
        raise ValueError(
            f"{model}['{app_name}'] has unknown keys: {', '.join(sorted(map(str, unknown_keys)))}"
        )
    if not raw:
        raise ValueError(
            f"{model}['{app_name}'] must define at least one of 'machines' or 'units'"
        )

    machines_raw = raw.get("machines", {})
    if not isinstance(machines_raw, dict):
        raise ValueError(
            f"{model}['{app_name}'].machines must be a dict, got {type(machines_raw).__name__}"
        )

    units_raw = raw.get("units", {})
    if not isinstance(units_raw, dict):
        raise ValueError(
            f"{model}['{app_name}'].units must be a dict, got {type(units_raw).__name__}"
        )

    machines = {
        str(machine_id): _parse_machine_entry(model, app_name, str(machine_id), entry)
        for machine_id, entry in machines_raw.items()
    }
    units = {
        str(unit_name): _parse_unit_entry(model, app_name, str(unit_name), entry)
        for unit_name, entry in units_raw.items()
    }
    return ApplicationConfig(machines=machines, units=units)


def parse_config(yaml_string: str) -> ParsedConfig:
    """Parse a role-mapping YAML config string into a ParsedConfig.

    The top-level keys are model names. Under each model, keys are
    application names, each with ``machines`` and/or ``units`` mappings.

    Args:
        yaml_string: The YAML string from the charm's role-mapping config option.

    Returns:
        A ParsedConfig with per-model machine and unit entries.

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
    if not raw:
        raise ValueError("role-mapping config must have at least one model")

    models: dict[str, ModelConfig] = {}
    for model_name, model_raw in raw.items():
        model_name = str(model_name)
        if not isinstance(model_raw, dict):
            raise ValueError(
                f"model '{model_name}' must be a dict, got {type(model_raw).__name__}"
            )

        applications = {
            str(app_name): _parse_application_entry(model_name, str(app_name), entry)
            for app_name, entry in model_raw.items()
        }

        models[model_name] = ModelConfig(applications=applications)

    return ParsedConfig(models=models)


def compute_assignments(
    config: ParsedConfig,
    model_name: str,
    registered_units: list[RegisteredUnit],
) -> dict[str, UnitRoleAssignment]:
    """Resolve per-unit role assignments for a specific model.

    Resolution precedence (from interface spec):
    1. Roles: unit-level fully replaces machine-level. No merging.
    2. workload-params: shallow merge. Machine-level is the base, unit-level
       overrides individual keys.
    3. Units without machine_id only receive unit-level config.

    Args:
        config: Parsed role-mapping configuration.
        model_name: The model name to resolve assignments for.
        registered_units: Units registered via the role-assignment relation.

    Returns:
        Dict mapping unit names to their resolved assignments. Every unit in
        registered_units gets an entry; unmatched units get status="pending".
    """
    model_cfg = config.models.get(model_name)

    assignments: dict[str, UnitRoleAssignment] = {}
    for unit in registered_units:
        if model_cfg is None:
            assignments[unit.unit_name] = UnitRoleAssignment(status=AssignmentStatus.PENDING)
            continue

        app_cfg = model_cfg.applications.get(unit.application_name)
        if app_cfg is None:
            assignments[unit.unit_name] = UnitRoleAssignment(status=AssignmentStatus.PENDING)
            continue

        unit_cfg = app_cfg.units.get(unit.unit_name)
        machine_cfg = (
            app_cfg.machines.get(unit.machine_id) if unit.machine_id is not None else None
        )

        # Resolve roles: unit-level wins, then machine-level, then no match.
        if unit_cfg is not None:
            roles = unit_cfg.roles
        elif machine_cfg is not None:
            roles = machine_cfg.roles
        else:
            assignments[unit.unit_name] = UnitRoleAssignment(status=AssignmentStatus.PENDING)
            continue

        # Resolve workload-params: machine base (scoped by app), unit overrides.
        resolved_params: dict[str, Any] = {}
        if machine_cfg is not None:
            resolved_params.update(machine_cfg.workload_params)
        if unit_cfg is not None:
            resolved_params.update(unit_cfg.workload_params)

        assignments[unit.unit_name] = UnitRoleAssignment(
            status=AssignmentStatus.ASSIGNED,
            roles=roles,
            workload_params=resolved_params or None,
        )
    return assignments


def get_unmatched_models(
    config: ParsedConfig,
    seen_models: set[str],
) -> set[str]:
    """Return model names in config that were not seen in any relation."""
    return set(config.models.keys()) - seen_models
