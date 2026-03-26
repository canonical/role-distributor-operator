"""Tests for role_distributor business logic module."""

from __future__ import annotations

import pytest

from role_distributor import (
    MachineConfig,
    ModelConfig,
    ParsedConfig,
    UnitConfig,
    parse_config,
)


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
            models={
                "my-model": ModelConfig(
                    machines={"0": MachineConfig(roles=("control",), workload_params={})},
                    units={"microceph/0": UnitConfig(roles=("gateway",), workload_params={})},
                ),
            },
        )
        assert "my-model" in pc.models
        assert "0" in pc.models["my-model"].machines
        assert "microceph/0" in pc.models["my-model"].units


class TestParseConfig:
    def test_single_model_machines_only(self):
        yaml_str = """
my-model:
  "0":
    roles: [control, storage]
"""
        result = parse_config(yaml_str)
        assert "my-model" in result.models
        mc = result.models["my-model"]
        assert "0" in mc.machines
        assert mc.machines["0"].roles == ("control", "storage")
        assert mc.units == {}

    def test_single_model_units_only(self):
        yaml_str = """
my-model:
  microceph/0:
    roles: [control, gateway]
"""
        result = parse_config(yaml_str)
        mc = result.models["my-model"]
        assert mc.machines == {}
        assert "microceph/0" in mc.units
        assert mc.units["microceph/0"].roles == ("control", "gateway")

    def test_single_model_mixed(self):
        yaml_str = """
my-model:
  "0":
    roles: [control, storage]
  microceph/0:
    roles: [gateway]
"""
        result = parse_config(yaml_str)
        mc = result.models["my-model"]
        assert "0" in mc.machines
        assert "microceph/0" in mc.units

    def test_multiple_models(self):
        yaml_str = """
model-a:
  "0":
    roles: [control]
model-b:
  "0":
    roles: [compute]
"""
        result = parse_config(yaml_str)
        assert "model-a" in result.models
        assert "model-b" in result.models
        assert result.models["model-a"].machines["0"].roles == ("control",)
        assert result.models["model-b"].machines["0"].roles == ("compute",)

    def test_machine_with_workload_params(self):
        yaml_str = """
my-model:
  "0":
    roles: [control]
    workload-params:
      microceph:
        flavors: [rgw]
      microovn:
        some-key: some-value
"""
        result = parse_config(yaml_str)
        mc = result.models["my-model"].machines["0"]
        assert mc.workload_params == {
            "microceph": {"flavors": ["rgw"]},
            "microovn": {"some-key": "some-value"},
        }

    def test_unit_with_workload_params(self):
        yaml_str = """
my-model:
  microceph/0:
    roles: [gateway]
    workload-params:
      flavors: [rgw, s3]
"""
        result = parse_config(yaml_str)
        uc = result.models["my-model"].units["microceph/0"]
        assert uc.workload_params == {"flavors": ["rgw", "s3"]}

    def test_empty_string_raises(self):
        with pytest.raises(ValueError, match="empty"):
            parse_config("")

    def test_malformed_yaml_raises(self):
        with pytest.raises(ValueError):
            parse_config("{{not: valid: yaml")

    def test_empty_dict_raises(self):
        with pytest.raises(ValueError, match="at least one model"):
            parse_config("{}")

    def test_model_value_not_a_dict_raises(self):
        with pytest.raises(ValueError, match="model.*must be a dict"):
            parse_config("my-model: not-a-dict")

    def test_machine_entry_not_a_dict_raises(self):
        with pytest.raises(ValueError, match="must be a dict"):
            parse_config("my-model:\n  '0': not-a-dict")

    def test_machine_roles_not_a_list_raises(self):
        with pytest.raises(ValueError, match="roles"):
            parse_config("my-model:\n  '0':\n    roles: not-a-list")

    def test_machine_roles_missing_raises(self):
        with pytest.raises(ValueError, match="roles"):
            parse_config("my-model:\n  '0':\n    workload-params: {}")

    def test_machine_workload_params_not_a_dict_raises(self):
        with pytest.raises(ValueError, match="workload-params must be a dict"):
            parse_config("my-model:\n  '0':\n    roles: [x]\n    workload-params: not-a-dict")

    def test_machine_workload_params_nested_value_not_a_dict_raises(self):
        with pytest.raises(ValueError, match="workload-params.*must be a dict"):
            parse_config(
                "my-model:\n  '0':\n    roles: [x]\n    workload-params:\n      app-a: not-a-dict"
            )

    def test_unit_entry_not_a_dict_raises(self):
        with pytest.raises(ValueError, match="must be a dict"):
            parse_config("my-model:\n  app/0: not-a-dict")

    def test_unit_roles_missing_raises(self):
        with pytest.raises(ValueError, match="missing required key.*roles"):
            parse_config("my-model:\n  app/0:\n    workload-params: {}")

    def test_unit_roles_not_a_list_raises(self):
        with pytest.raises(ValueError, match="roles must be a list"):
            parse_config("my-model:\n  app/0:\n    roles: not-a-list")

    def test_unit_workload_params_not_a_dict_raises(self):
        with pytest.raises(ValueError, match="workload-params must be a dict"):
            parse_config("my-model:\n  app/0:\n    roles: [x]\n    workload-params: not-a-dict")

    def test_yaml_not_a_dict_raises(self):
        with pytest.raises(ValueError):
            parse_config("- a list\n- not a dict")


from charms.role_distributor.v0.role_assignment import (
    RegisteredUnit,
    UnitRoleAssignment,
)

from role_distributor import compute_assignments, get_unmatched_models


class TestComputeAssignments:
    def test_unit_level_match(self):
        """Unit with matching unit-level config gets assigned."""
        config = ParsedConfig(
            models={
                "ceph-model": ModelConfig(
                    machines={},
                    units={
                        "microceph/0": UnitConfig(
                            roles=("control", "storage"), workload_params={}
                        ),
                    },
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
        result = compute_assignments(config, "ceph-model", units)
        assert result["microceph/0"] == UnitRoleAssignment(
            status="assigned", roles=("control", "storage")
        )

    def test_machine_level_match(self):
        """Unit with machine-id gets roles from machine-level config."""
        config = ParsedConfig(
            models={
                "ceph-model": ModelConfig(
                    machines={
                        "0": MachineConfig(roles=("control", "storage"), workload_params={}),
                    },
                    units={},
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
        result = compute_assignments(config, "ceph-model", units)
        assert result["microceph/0"] == UnitRoleAssignment(
            status="assigned", roles=("control", "storage")
        )

    def test_unit_level_roles_override_machine_level(self):
        """Unit-level roles fully replace machine-level roles."""
        config = ParsedConfig(
            models={
                "m": ModelConfig(
                    machines={
                        "0": MachineConfig(roles=("control", "storage"), workload_params={}),
                    },
                    units={
                        "microceph/0": UnitConfig(roles=("gateway",), workload_params={}),
                    },
                ),
            },
        )
        units = [
            RegisteredUnit(
                unit_name="microceph/0",
                model_name="m",
                application_name="microceph",
                machine_id="0",
            ),
        ]
        result = compute_assignments(config, "m", units)
        assert result["microceph/0"].roles == ("gateway",)

    def test_workload_params_shallow_merge(self):
        """Machine-level params are base, unit-level overrides individual keys."""
        config = ParsedConfig(
            models={
                "m": ModelConfig(
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
                ),
            },
        )
        units = [
            RegisteredUnit(
                unit_name="microceph/0",
                model_name="m",
                application_name="microceph",
                machine_id="0",
            ),
        ]
        result = compute_assignments(config, "m", units)
        assert result["microceph/0"].workload_params == {
            "flavors": ["rgw", "s3"],
            "region": "us-east",
        }

    def test_workload_params_none_when_empty(self):
        """workload_params is None when resolved dict is empty."""
        config = ParsedConfig(
            models={
                "m": ModelConfig(
                    machines={},
                    units={
                        "microceph/0": UnitConfig(roles=("control",), workload_params={}),
                    },
                ),
            },
        )
        units = [
            RegisteredUnit(
                unit_name="microceph/0",
                model_name="m",
                application_name="microceph",
            ),
        ]
        result = compute_assignments(config, "m", units)
        assert result["microceph/0"].workload_params is None

    def test_machine_workload_params_scoped_by_app_name(self):
        """Machine-level workload-params are scoped by application name."""
        config = ParsedConfig(
            models={
                "m": ModelConfig(
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
                ),
            },
        )
        ceph_unit = RegisteredUnit(
            unit_name="microceph/0",
            model_name="m",
            application_name="microceph",
            machine_id="0",
        )
        ovn_unit = RegisteredUnit(
            unit_name="microovn/0",
            model_name="m",
            application_name="microovn",
            machine_id="0",
        )
        result = compute_assignments(config, "m", [ceph_unit, ovn_unit])
        assert result["microceph/0"].workload_params == {"flavors": ["rgw"]}
        assert result["microovn/0"].workload_params == {"some-key": "some-value"}

    def test_unit_without_machine_id_skips_machine_config(self):
        """Unit without machine-id only gets unit-level config."""
        config = ParsedConfig(
            models={
                "m": ModelConfig(
                    machines={
                        "0": MachineConfig(roles=("control",), workload_params={}),
                    },
                    units={},
                ),
            },
        )
        units = [
            RegisteredUnit(
                unit_name="microceph/0",
                model_name="m",
                application_name="microceph",
                machine_id=None,
            ),
        ]
        result = compute_assignments(config, "m", units)
        assert result["microceph/0"] == UnitRoleAssignment(status="pending")

    def test_no_match_returns_pending(self):
        """Unit with no matching config gets pending status."""
        config = ParsedConfig(
            models={"m": ModelConfig(machines={}, units={})},
        )
        units = [
            RegisteredUnit(
                unit_name="microceph/0",
                model_name="m",
                application_name="microceph",
            ),
        ]
        result = compute_assignments(config, "m", units)
        assert result["microceph/0"] == UnitRoleAssignment(status="pending")

    def test_unknown_model_returns_pending(self):
        """Units from a model not in config get pending status."""
        config = ParsedConfig(
            models={
                "model-a": ModelConfig(
                    machines={"0": MachineConfig(roles=("control",), workload_params={})},
                    units={},
                ),
            },
        )
        units = [
            RegisteredUnit(
                unit_name="microceph/0",
                model_name="model-b",
                application_name="microceph",
                machine_id="0",
            ),
        ]
        result = compute_assignments(config, "model-b", units)
        assert result["microceph/0"] == UnitRoleAssignment(status="pending")

    def test_multiple_units_mixed(self):
        """Multiple units with different match states."""
        config = ParsedConfig(
            models={
                "m": ModelConfig(
                    machines={},
                    units={
                        "microceph/0": UnitConfig(roles=("control",), workload_params={}),
                    },
                ),
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
        result = compute_assignments(config, "m", units)
        assert result["microceph/0"].status == "assigned"
        assert result["microceph/1"].status == "pending"

    def test_machine_only_workload_params_for_app(self):
        """Machine-level workload-params applied when no unit-level params exist."""
        config = ParsedConfig(
            models={
                "m": ModelConfig(
                    machines={
                        "0": MachineConfig(
                            roles=("control",),
                            workload_params={"microceph": {"flavors": ["rgw"]}},
                        ),
                    },
                    units={},
                ),
            },
        )
        units = [
            RegisteredUnit(
                unit_name="microceph/0",
                model_name="m",
                application_name="microceph",
                machine_id="0",
            ),
        ]
        result = compute_assignments(config, "m", units)
        assert result["microceph/0"].workload_params == {"flavors": ["rgw"]}

    def test_machine_workload_params_missing_app_entry(self):
        """Machine has workload-params but not for this unit's application."""
        config = ParsedConfig(
            models={
                "m": ModelConfig(
                    machines={
                        "0": MachineConfig(
                            roles=("control",),
                            workload_params={"microovn": {"key": "val"}},
                        ),
                    },
                    units={},
                ),
            },
        )
        units = [
            RegisteredUnit(
                unit_name="microceph/0",
                model_name="m",
                application_name="microceph",
                machine_id="0",
            ),
        ]
        result = compute_assignments(config, "m", units)
        assert result["microceph/0"].workload_params is None
        assert result["microceph/0"].roles == ("control",)

    def test_cross_model_isolation(self):
        """Config for model-a does not affect units from model-b."""
        config = ParsedConfig(
            models={
                "model-a": ModelConfig(
                    machines={"0": MachineConfig(roles=("control",), workload_params={})},
                    units={},
                ),
                "model-b": ModelConfig(
                    machines={"0": MachineConfig(roles=("compute",), workload_params={})},
                    units={},
                ),
            },
        )
        units_a = [
            RegisteredUnit(
                unit_name="app/0",
                model_name="model-a",
                application_name="app",
                machine_id="0",
            ),
        ]
        units_b = [
            RegisteredUnit(
                unit_name="app/0",
                model_name="model-b",
                application_name="app",
                machine_id="0",
            ),
        ]
        result_a = compute_assignments(config, "model-a", units_a)
        result_b = compute_assignments(config, "model-b", units_b)
        assert result_a["app/0"].roles == ("control",)
        assert result_b["app/0"].roles == ("compute",)


class TestGetUnmatchedModels:
    def test_all_matched(self):
        config = ParsedConfig(
            models={
                "model-a": ModelConfig(machines={}, units={}),
                "model-b": ModelConfig(machines={}, units={}),
            },
        )
        assert get_unmatched_models(config, {"model-a", "model-b"}) == set()

    def test_some_unmatched(self):
        config = ParsedConfig(
            models={
                "model-a": ModelConfig(machines={}, units={}),
                "model-b": ModelConfig(machines={}, units={}),
            },
        )
        assert get_unmatched_models(config, {"model-a"}) == {"model-b"}

    def test_none_matched(self):
        config = ParsedConfig(
            models={
                "model-a": ModelConfig(machines={}, units={}),
            },
        )
        assert get_unmatched_models(config, set()) == {"model-a"}
