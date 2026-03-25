#!/usr/bin/env python3
"""Dummy requirer charm for integration testing role-assignment."""

from __future__ import annotations

import json

import ops
from charms.role_distributor.v0.role_assignment import RoleAssignmentRequirer


class DummyRequirerCharm(ops.CharmBase):
    """Minimal charm that consumes role-assignment and validates assignments."""

    def __init__(self, framework: ops.Framework):
        super().__init__(framework)
        self._requirer = RoleAssignmentRequirer(self, "role-assignment")
        framework.observe(
            self._requirer.on.role_assignment_changed,
            self._on_role_assignment_changed,
        )
        framework.observe(
            self._requirer.on.role_assignment_revoked,
            self._on_role_assignment_revoked,
        )
        framework.observe(self.on.get_assignment_action, self._on_get_assignment)
        framework.observe(self.on.install, self._on_install)

    def _on_install(self, _event: ops.EventBase) -> None:
        self.unit.status = ops.WaitingStatus("no assignment")

    def _on_role_assignment_changed(self, event: ops.EventBase) -> None:
        assignment = self._requirer.get_assignment()
        if assignment is None:
            return
        if assignment.status != "assigned":
            self.unit.status = ops.BlockedStatus(f"invalid assignment: status={assignment.status}")
            return
        if not assignment.roles:
            self.unit.status = ops.BlockedStatus("invalid assignment: empty roles")
            return
        self.unit.status = ops.ActiveStatus(f"roles: {','.join(assignment.roles)}")

    def _on_role_assignment_revoked(self, _event: ops.EventBase) -> None:
        self.unit.status = ops.WaitingStatus("no assignment")

    def _on_get_assignment(self, event: ops.ActionEvent) -> None:
        assignment = self._requirer.get_assignment()
        if assignment is None:
            event.set_results({"assignment": json.dumps(None)})
            return
        event.set_results({"assignment": json.dumps(assignment.to_dict())})


if __name__ == "__main__":
    ops.main(DummyRequirerCharm)
