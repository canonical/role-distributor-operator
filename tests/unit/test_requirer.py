"""Tests for RoleAssignmentRequirer."""

from __future__ import annotations

import json

import ops
import ops.testing

from lib.charms.role_distributor.v0.role_assignment import (
    RoleAssignmentChangedEvent,
    RoleAssignmentRequirer,
    RoleAssignmentRevokedEvent,
)

# ---------------------------------------------------------------------------
# Capture buffers (module-level so charm instances can write to them even
# though ops.testing does not expose ctx.charm after ctx.run()).
# ---------------------------------------------------------------------------
_events_received: list = []
_get_assignment_results: list = []


def _reset_captures() -> None:
    _events_received.clear()
    _get_assignment_results.clear()


# ---------------------------------------------------------------------------
# Minimal test charm for Requirer side
# ---------------------------------------------------------------------------
class RequirerCharm(ops.CharmBase):
    META = {
        "name": "test-requirer",
        "requires": {"role-assignment": {"interface": "role-assignment", "limit": 1}},
    }

    def __init__(self, framework: ops.Framework):
        super().__init__(framework)
        self.role_assignment = RoleAssignmentRequirer(self, "role-assignment")
        self.framework.observe(
            self.role_assignment.on.role_assignment_changed,
            self._on_changed,
        )
        self.framework.observe(
            self.role_assignment.on.role_assignment_revoked,
            self._on_revoked,
        )

    def _on_changed(self, event: RoleAssignmentChangedEvent):
        _events_received.append(
            ("changed", event.status, event.roles, event.message, event.workload_params)
        )

    def _on_revoked(self, event: RoleAssignmentRevokedEvent):
        _events_received.append(("revoked",))


class RequirerCharmWithGetCapture(ops.CharmBase):
    """Variant that captures get_assignment() results during relation_changed."""

    META = RequirerCharm.META

    def __init__(self, framework: ops.Framework):
        super().__init__(framework)
        self.role_assignment = RoleAssignmentRequirer(self, "role-assignment")
        self.framework.observe(
            self.on["role-assignment"].relation_changed,
            self._on_rel_changed,
        )

    def _on_rel_changed(self, event: ops.RelationChangedEvent):
        _get_assignment_results.append(self.role_assignment.get_assignment())


class StartCaptureCharm(ops.CharmBase):
    """Variant that captures get_assignment() on start (no relation needed)."""

    META = RequirerCharm.META

    def __init__(self, framework: ops.Framework):
        super().__init__(framework)
        self.role_assignment = RoleAssignmentRequirer(self, "role-assignment")
        self.framework.observe(self.on.start, self._on_start)

    def _on_start(self, event: ops.StartEvent):
        _get_assignment_results.append(self.role_assignment.get_assignment())


# ---------------------------------------------------------------------------
# Registration tests
# ---------------------------------------------------------------------------
class TestRequirerRegistration:
    def setup_method(self):
        _reset_captures()

    def test_unit_databag_written_on_joined(self):
        """On relation-joined, the unit writes unit-name to its databag."""
        ctx = ops.testing.Context(RequirerCharm, meta=RequirerCharm.META)
        relation = ops.testing.Relation(
            endpoint="role-assignment",
            interface="role-assignment",
        )
        state = ops.testing.State(relations=[relation])
        out = ctx.run(ctx.on.relation_joined(relation), state)
        rel = out.get_relation(relation.id)
        local_unit_data = rel.local_unit_data
        assert "unit-name" in local_unit_data
        assert local_unit_data["unit-name"] == "test-requirer/0"

    def test_app_databag_written_on_joined_by_leader(self):
        """Leader writes model-name and application-name to app databag on join."""
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

    def test_unit_databag_does_not_write_machine_id_on_k8s(self):
        """machine-id is not written when JUJU_MACHINE_ID is absent (e.g. k8s)."""
        ctx = ops.testing.Context(RequirerCharm, meta=RequirerCharm.META)
        relation = ops.testing.Relation(
            endpoint="role-assignment",
            interface="role-assignment",
        )
        state = ops.testing.State(relations=[relation])
        out = ctx.run(ctx.on.relation_joined(relation), state)
        rel = out.get_relation(relation.id)
        assert "machine-id" not in rel.local_unit_data

    def test_unit_databag_writes_machine_id_on_machine_charm(self):
        """machine-id is auto-populated when running on a machine."""
        ctx = ops.testing.Context(RequirerCharm, meta=RequirerCharm.META, machine_id="42")
        relation = ops.testing.Relation(
            endpoint="role-assignment",
            interface="role-assignment",
        )
        state = ops.testing.State(relations=[relation])
        out = ctx.run(ctx.on.relation_joined(relation), state)
        rel = out.get_relation(relation.id)
        assert rel.local_unit_data["machine-id"] == "42"

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


# ---------------------------------------------------------------------------
# get_assignment() tests
# ---------------------------------------------------------------------------
class TestRequirerGetAssignment:
    def setup_method(self):
        _reset_captures()

    def test_get_assignment_returns_none_when_no_assignments_key(self):
        """When Provider App databag has no assignments key, return None."""
        ctx = ops.testing.Context(
            RequirerCharmWithGetCapture, meta=RequirerCharmWithGetCapture.META
        )
        relation = ops.testing.Relation(
            endpoint="role-assignment",
            interface="role-assignment",
        )
        state = ops.testing.State(relations=[relation])
        ctx.run(ctx.on.relation_changed(relation), state)
        assert len(_get_assignment_results) == 1
        assert _get_assignment_results[0] is None

    def test_get_assignment_returns_assignment_when_present(self):
        """When Provider App databag has an assignment for this unit, return it."""
        ctx = ops.testing.Context(
            RequirerCharmWithGetCapture, meta=RequirerCharmWithGetCapture.META
        )
        assignments = {"test-requirer/0": {"status": "assigned", "roles": ["control"]}}
        relation = ops.testing.Relation(
            endpoint="role-assignment",
            interface="role-assignment",
            remote_app_data={"assignments": json.dumps(assignments)},
        )
        state = ops.testing.State(relations=[relation])
        ctx.run(ctx.on.relation_changed(relation), state)
        assert len(_get_assignment_results) == 1
        result = _get_assignment_results[0]
        assert result is not None
        assert result.status == "assigned"
        assert result.roles == ("control",)

    def test_get_assignment_returns_none_when_unit_not_in_map(self):
        """When assignment map exists but has no entry for this unit."""
        ctx = ops.testing.Context(
            RequirerCharmWithGetCapture, meta=RequirerCharmWithGetCapture.META
        )
        assignments = {"other-app/0": {"status": "assigned", "roles": ["storage"]}}
        relation = ops.testing.Relation(
            endpoint="role-assignment",
            interface="role-assignment",
            remote_app_data={"assignments": json.dumps(assignments)},
        )
        state = ops.testing.State(relations=[relation])
        ctx.run(ctx.on.relation_changed(relation), state)
        assert len(_get_assignment_results) == 1
        assert _get_assignment_results[0] is None


# ---------------------------------------------------------------------------
# Event-emission tests
# ---------------------------------------------------------------------------
class TestRequirerEvents:
    def setup_method(self):
        _reset_captures()

    def test_changed_event_emitted_on_new_assignment(self):
        """RoleAssignmentChangedEvent fires when assignment appears."""
        ctx = ops.testing.Context(RequirerCharm, meta=RequirerCharm.META)
        assignments = {"test-requirer/0": {"status": "assigned", "roles": ["control"]}}
        relation = ops.testing.Relation(
            endpoint="role-assignment",
            interface="role-assignment",
            remote_app_data={"assignments": json.dumps(assignments)},
        )
        state = ops.testing.State(relations=[relation])
        ctx.run(ctx.on.relation_changed(relation), state)
        assert len(_events_received) == 1
        assert _events_received[0] == ("changed", "assigned", ("control",), None, None)

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
            "changed",
            "assigned",
            ("gateway",),
            None,
            {"flavors": ["rgw"]},
        )

    def test_changed_event_always_emitted(self):
        """The library is stateless — changed fires on every relation-changed.

        Carries a valid assignment. Charms handle their own idempotency.
        """
        ctx = ops.testing.Context(RequirerCharm, meta=RequirerCharm.META)
        assignments = {"test-requirer/0": {"status": "assigned", "roles": ["control"]}}
        relation = ops.testing.Relation(
            endpoint="role-assignment",
            interface="role-assignment",
            remote_app_data={"assignments": json.dumps(assignments)},
        )
        state = ops.testing.State(relations=[relation])
        ctx.run(ctx.on.relation_changed(relation), state)
        assert len(_events_received) == 1
        assert _events_received[0] == ("changed", "assigned", ("control",), None, None)

    def test_revoked_event_on_relation_broken(self):
        """RoleAssignmentRevokedEvent fires on relation-broken."""
        ctx = ops.testing.Context(RequirerCharm, meta=RequirerCharm.META)
        relation = ops.testing.Relation(
            endpoint="role-assignment",
            interface="role-assignment",
        )
        state = ops.testing.State(relations=[relation])
        ctx.run(ctx.on.relation_broken(relation), state)
        assert len(_events_received) == 1
        assert _events_received[0] == ("revoked",)


# ---------------------------------------------------------------------------
# Edge case tests
# ---------------------------------------------------------------------------
class TestRequirerEdgeCases:
    def setup_method(self):
        _reset_captures()

    def test_malformed_json_returns_none(self):
        """Malformed assignments JSON is handled gracefully."""
        ctx = ops.testing.Context(
            RequirerCharmWithGetCapture, meta=RequirerCharmWithGetCapture.META
        )
        relation = ops.testing.Relation(
            endpoint="role-assignment",
            interface="role-assignment",
            remote_app_data={"assignments": "not valid json{{{"},
        )
        state = ops.testing.State(relations=[relation])
        ctx.run(ctx.on.relation_changed(relation), state)
        assert len(_get_assignment_results) == 1
        assert _get_assignment_results[0] is None

    def test_get_assignment_no_relation(self):
        """get_assignment returns None when no relation exists."""
        ctx = ops.testing.Context(StartCaptureCharm, meta=StartCaptureCharm.META)
        state = ops.testing.State()
        ctx.run(ctx.on.start(), state)
        assert len(_get_assignment_results) == 1
        assert _get_assignment_results[0] is None

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
        assert _events_received[0] == ("changed", "error", (), "not in topology", None)

    def test_no_event_when_entry_absent(self):
        """No event when this unit has no entry in the assignments map.

        The stateless library does not track previous state, so it cannot
        detect entry disappearance. Only relation-broken triggers revocation.
        """
        ctx = ops.testing.Context(RequirerCharm, meta=RequirerCharm.META)
        relation = ops.testing.Relation(
            endpoint="role-assignment",
            interface="role-assignment",
            remote_app_data={"assignments": json.dumps({})},
        )
        state = ops.testing.State(relations=[relation])
        ctx.run(ctx.on.relation_changed(relation), state)
        assert len(_events_received) == 0

    def test_no_revoked_event_on_remote_unit_departed(self):
        """relation-departed for a remote Provider unit does NOT emit revoked.

        In Juju, relation-departed fires when a remote unit leaves.
        The Requirer's assignment may still be valid (via the Provider
        App databag). Only relation-broken should trigger revocation.
        """
        ctx = ops.testing.Context(RequirerCharm, meta=RequirerCharm.META)
        relation = ops.testing.Relation(
            endpoint="role-assignment",
            interface="role-assignment",
        )
        state = ops.testing.State(relations=[relation])
        ctx.run(ctx.on.relation_departed(relation, remote_unit=0), state)
        assert len(_events_received) == 0
