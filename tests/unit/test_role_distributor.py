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

    def test_machine_entry_not_a_dict_raises(self):
        with pytest.raises(ValueError, match="machines.*must be a dict"):
            parse_config("machines:\n  '0': not-a-dict")

    def test_machine_workload_params_not_a_dict_raises(self):
        with pytest.raises(ValueError, match="workload-params must be a dict"):
            parse_config("machines:\n  '0':\n    roles: [x]\n    workload-params: not-a-dict")

    def test_machine_workload_params_nested_value_not_a_dict_raises(self):
        with pytest.raises(ValueError, match="workload-params.*must be a dict"):
            parse_config(
                "machines:\n  '0':\n    roles: [x]\n    workload-params:\n      app-a: not-a-dict"
            )

    def test_units_value_not_a_dict_raises(self):
        with pytest.raises(ValueError):
            parse_config("units: not-a-dict")

    def test_unit_entry_not_a_dict_raises(self):
        with pytest.raises(ValueError, match="units.*must be a dict"):
            parse_config("units:\n  app/0: not-a-dict")

    def test_unit_roles_missing_raises(self):
        with pytest.raises(ValueError, match="missing required key.*roles"):
            parse_config("units:\n  app/0:\n    workload-params: {}")

    def test_unit_roles_not_a_list_raises(self):
        with pytest.raises(ValueError, match="roles must be a list"):
            parse_config("units:\n  app/0:\n    roles: not-a-list")

    def test_unit_workload_params_not_a_dict_raises(self):
        with pytest.raises(ValueError, match="workload-params must be a dict"):
            parse_config("units:\n  app/0:\n    roles: [x]\n    workload-params: not-a-dict")

    def test_yaml_not_a_dict_raises(self):
        with pytest.raises(ValueError):
            parse_config("- a list\n- not a dict")


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
                "microceph/0": UnitConfig(roles=("control", "storage"), workload_params={}),
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
