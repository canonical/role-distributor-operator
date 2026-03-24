"""Tests for RoleAssignmentProvider."""

from __future__ import annotations

import json

import ops
import ops.testing

from lib.charms.role_distributor.v0.role_assignment import (
    RoleAssignmentProvider,
    RoleAssignmentUnitDepartedEvent,
    RoleAssignmentUnitRegisteredEvent,
    UnitRoleAssignment,
)

# Module-level capture buffers
_events_received: list = []
_registered_units_results: list = []


def _reset_captures() -> None:
    _events_received.clear()
    _registered_units_results.clear()


class ProviderCharm(ops.CharmBase):
    META = {
        "name": "role-distributor",
        "provides": {"role-assignment": {"interface": "role-assignment"}},
    }

    def __init__(self, framework: ops.Framework):
        super().__init__(framework)
        self.role_assignment = RoleAssignmentProvider(self, "role-assignment")
        self.framework.observe(
            self.role_assignment.on.unit_registered,
            self._on_registered,
        )
        self.framework.observe(
            self.role_assignment.on.unit_departed,
            self._on_departed,
        )

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


class ProviderCharmWithGetCapture(ops.CharmBase):
    """Variant that captures get_registered_units() during relation_changed."""

    META = ProviderCharm.META

    def __init__(self, framework: ops.Framework):
        super().__init__(framework)
        self.role_assignment = RoleAssignmentProvider(self, "role-assignment")
        self.framework.observe(
            self.on["role-assignment"].relation_changed,
            self._on_rel_changed,
        )

    def _on_rel_changed(self, event: ops.RelationChangedEvent):
        rel = self.model.get_relation("role-assignment")
        if rel:
            _registered_units_results.append(self.role_assignment.get_registered_units(rel))


class TestProviderGetRegisteredUnits:
    def setup_method(self):
        _reset_captures()

    def test_get_registered_units_empty(self):
        """No units registered yet returns empty list."""
        ctx = ops.testing.Context(
            ProviderCharmWithGetCapture, meta=ProviderCharmWithGetCapture.META
        )
        relation = ops.testing.Relation(
            endpoint="role-assignment",
            interface="role-assignment",
        )
        state = ops.testing.State(relations=[relation], leader=True)
        ctx.run(ctx.on.relation_changed(relation), state)
        assert len(_registered_units_results) == 1
        assert _registered_units_results[0] == []

    def test_get_registered_units_reads_remote_databags(self):
        """Read unit-name/machine-id from unit databags, model-name/application-name from app."""
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
        by_name = {u.unit_name: u for u in units}
        assert by_name["microceph/0"].machine_id == "0"
        assert by_name["microceph/1"].machine_id is None


class TestProviderSetAssignments:
    def setup_method(self):
        _reset_captures()

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


class TestProviderEvents:
    def setup_method(self):
        _reset_captures()

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
        assert ("registered", "microceph/0", "ceph-model", "microceph", "3") in _events_received

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
        assert ("registered", "microceph/0", "ceph-model", "microceph", None) in _events_received

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
        assert ("registered", "microceph/0", "ceph-model", "microceph", "2") in _events_received


# ---------------------------------------------------------------------------
# Edge case tests
# ---------------------------------------------------------------------------
class TestProviderEdgeCases:
    def setup_method(self):
        _reset_captures()

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
