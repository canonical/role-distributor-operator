#!/usr/bin/env python3
# Copyright 2026 guillaume.boutry@canonical.com
# See LICENSE file for licensing details.

"""Role Distributor charm."""

from __future__ import annotations

import logging

import ops
from charms.role_distributor.v0.role_assignment import AssignmentStatus, RoleAssignmentProvider

import role_distributor

logger = logging.getLogger(__name__)


class RoleDistributorCharm(ops.CharmBase):
    """Charm that distributes roles to related applications.

    The operator provides a YAML config blob with model-scoped machine-level
    and unit-level role mappings. The charm resolves and publishes per-unit
    assignments to all related applications through the role-assignment
    interface.
    """

    def __init__(self, framework: ops.Framework):
        super().__init__(framework)
        self._provider = RoleAssignmentProvider(self, "role-assignment")
        framework.observe(self.on.config_changed, self._reconcile)
        framework.observe(self.on["role-assignment"].relation_changed, self._reconcile)
        framework.observe(self.on["role-assignment"].relation_departed, self._reconcile)
        framework.observe(self.on.leader_elected, self._reconcile)

    def _reconcile(self, _event: ops.EventBase) -> None:
        """Re-evaluate and publish role assignments on all relations."""
        if not self.unit.is_leader():
            self.unit.status = ops.ActiveStatus()
            return

        raw_config = str(self.config.get("role-mapping", ""))
        if not raw_config.strip():
            self.unit.status = ops.BlockedStatus("no role-mapping config provided")
            return

        try:
            parsed = role_distributor.parse_config(raw_config)
        except ValueError as e:
            self.unit.status = ops.BlockedStatus(f"invalid role-mapping config: {e}")
            return

        total_pending = 0
        seen_models: set[str] = set()
        for relation in self.model.relations.get("role-assignment", []):
            registered = self._provider.get_registered_units(relation)
            if registered:
                model_name = registered[0].model_name
                seen_models.add(model_name)
            else:
                model_name = ""
            assignments = role_distributor.compute_assignments(parsed, model_name, registered)
            self._provider.set_assignments(relation, assignments)
            total_pending += sum(
                1 for a in assignments.values() if a.status is AssignmentStatus.PENDING
            )

        unmatched = role_distributor.get_unmatched_models(parsed, seen_models)
        if unmatched:
            logger.warning("Config references models not seen in any relation: %s", unmatched)

        messages = []
        if total_pending > 0:
            messages.append(f"units awaiting assignment: {total_pending}")
        if unmatched:
            messages.append(f"unmatched models: {', '.join(sorted(unmatched))}")

        if messages:
            self.unit.status = ops.WaitingStatus("; ".join(messages))
        else:
            self.unit.status = ops.ActiveStatus()


if __name__ == "__main__":  # pragma: nocover
    ops.main(RoleDistributorCharm)
