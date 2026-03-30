"""Tests for role-assignment data classes."""

from __future__ import annotations

import pytest

from lib.charms.role_distributor.v0.role_assignment import (
    AssignmentStatus,
    RegisteredUnit,
    UnitRoleAssignment,
)


class TestUnitRoleAssignment:
    def test_assigned_with_roles(self):
        a = UnitRoleAssignment(status=AssignmentStatus.ASSIGNED, roles=("control", "storage"))
        assert a.status is AssignmentStatus.ASSIGNED
        assert a.roles == ("control", "storage")
        assert a.message is None

    def test_pending_defaults(self):
        a = UnitRoleAssignment(status=AssignmentStatus.PENDING)
        assert a.status is AssignmentStatus.PENDING
        assert a.roles == ()
        assert a.message is None

    def test_error_with_message(self):
        a = UnitRoleAssignment(status=AssignmentStatus.ERROR, message="unit not found in topology")
        assert a.status is AssignmentStatus.ERROR
        assert a.roles == ()
        assert a.message == "unit not found in topology"

    def test_frozen(self):
        a = UnitRoleAssignment(status=AssignmentStatus.ASSIGNED, roles=("control",))
        with pytest.raises(AttributeError):
            a.status = AssignmentStatus.PENDING  # type: ignore[misc]

    def test_to_dict_assigned(self):
        a = UnitRoleAssignment(status=AssignmentStatus.ASSIGNED, roles=("control",))
        d = a.to_dict()
        assert d == {"status": "assigned", "roles": ["control"]}
        assert "message" not in d

    def test_to_dict_error(self):
        a = UnitRoleAssignment(status=AssignmentStatus.ERROR, message="bad")
        d = a.to_dict()
        assert d == {"status": "error", "message": "bad"}
        assert "roles" not in d

    def test_to_dict_pending(self):
        a = UnitRoleAssignment(status=AssignmentStatus.PENDING)
        d = a.to_dict()
        assert d == {"status": "pending"}

    def test_from_dict_assigned(self):
        a = UnitRoleAssignment.from_dict({"status": "assigned", "roles": ["storage"]})
        assert a.status is AssignmentStatus.ASSIGNED
        assert a.roles == ("storage",)

    def test_from_dict_strips_roles_for_non_assigned(self):
        """Roles field is ignored when status is not assigned."""
        a = UnitRoleAssignment.from_dict(
            {"status": "error", "message": "oops", "roles": ["stale"]}
        )
        assert a.status is AssignmentStatus.ERROR
        assert a.roles == ()

    def test_from_dict_error(self):
        a = UnitRoleAssignment.from_dict({"status": "error", "message": "oops"})
        assert a.status is AssignmentStatus.ERROR
        assert a.message == "oops"

    def test_from_dict_pending(self):
        a = UnitRoleAssignment.from_dict({"status": "pending"})
        assert a.status is AssignmentStatus.PENDING

    def test_from_dict_unknown_status_treated_as_pending(self):
        a = UnitRoleAssignment.from_dict({"status": "future-state"})
        assert a.status is AssignmentStatus.PENDING
        assert a.roles == ()

    def test_equality(self):
        a = UnitRoleAssignment(status=AssignmentStatus.ASSIGNED, roles=("control",))
        b = UnitRoleAssignment(status=AssignmentStatus.ASSIGNED, roles=("control",))
        assert a == b

    def test_inequality(self):
        a = UnitRoleAssignment(status=AssignmentStatus.ASSIGNED, roles=("control",))
        b = UnitRoleAssignment(status=AssignmentStatus.ASSIGNED, roles=("storage",))
        assert a != b

    def test_assigned_with_workload_params(self):
        a = UnitRoleAssignment(
            status=AssignmentStatus.ASSIGNED,
            roles=("control", "gateway"),
            workload_params={"flavors": ["rgw"]},
        )
        assert a.status is AssignmentStatus.ASSIGNED
        assert a.roles == ("control", "gateway")
        assert a.workload_params == {"flavors": ["rgw"]}

    def test_workload_params_defaults_to_none(self):
        a = UnitRoleAssignment(status=AssignmentStatus.ASSIGNED, roles=("control",))
        assert a.workload_params is None

    def test_to_dict_assigned_with_workload_params(self):
        a = UnitRoleAssignment(
            status=AssignmentStatus.ASSIGNED,
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
        a = UnitRoleAssignment(status=AssignmentStatus.ASSIGNED, roles=("control",))
        d = a.to_dict()
        assert "workload-params" not in d

    def test_to_dict_pending_no_workload_params(self):
        """workload-params is only serialized for assigned status."""
        a = UnitRoleAssignment(status=AssignmentStatus.PENDING, workload_params={"key": "val"})
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
        assert a.status is AssignmentStatus.ASSIGNED
        assert a.roles == ("gateway",)
        assert a.workload_params == {"flavors": ["rgw"]}

    def test_from_dict_without_workload_params(self):
        a = UnitRoleAssignment.from_dict({"status": "assigned", "roles": ["storage"]})
        assert a.workload_params is None

    def test_from_dict_strips_workload_params_for_non_assigned(self):
        """workload-params is ignored when status is not assigned."""
        a = UnitRoleAssignment.from_dict({"status": "pending", "workload-params": {"key": "val"}})
        assert a.workload_params is None


class TestRegisteredUnit:
    def test_creation(self):
        u = RegisteredUnit(
            unit_name="microceph/0",
            model_name="ceph-model",
            application_name="microceph",
        )
        assert u.unit_name == "microceph/0"
        assert u.model_name == "ceph-model"
        assert u.application_name == "microceph"

    def test_frozen(self):
        u = RegisteredUnit(
            unit_name="microceph/0",
            model_name="ceph-model",
            application_name="microceph",
        )
        with pytest.raises(AttributeError):
            u.unit_name = "other/1"  # type: ignore[misc]

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
