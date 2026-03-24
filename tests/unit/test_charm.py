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
        ctx = ops.testing.Context(RoleDistributorCharm, meta=CHARM_META, config=CHARM_CONFIG)
        state = ops.testing.State(leader=True)
        out = ctx.run(ctx.on.config_changed(), state)
        assert out.unit_status == ops.testing.BlockedStatus("no role-mapping config provided")

    def test_invalid_yaml_sets_blocked(self):
        """Invalid YAML in role-mapping -> BlockedStatus with error."""
        ctx = ops.testing.Context(
            RoleDistributorCharm,
            meta=CHARM_META,
            config=CHARM_CONFIG,
        )
        state = ops.testing.State(
            leader=True,
            config={"role-mapping": "{{invalid yaml"},
        )
        out = ctx.run(ctx.on.config_changed(), state)
        assert isinstance(out.unit_status, ops.testing.BlockedStatus)
        assert "invalid role-mapping config" in out.unit_status.message

    def test_valid_config_no_relations_sets_active(self):
        """Valid config but no relations -> ActiveStatus (no pending units)."""
        ctx = ops.testing.Context(
            RoleDistributorCharm,
            meta=CHARM_META,
            config=CHARM_CONFIG,
        )
        state = ops.testing.State(
            leader=True,
            config={"role-mapping": CONFIG_UNITS_ONLY},
        )
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
            config=CHARM_CONFIG,
        )
        state = ops.testing.State(
            relations=[relation],
            leader=True,
            config={"role-mapping": CONFIG_UNITS_ONLY},
        )
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
            config=CHARM_CONFIG,
        )
        state = ops.testing.State(
            relations=[relation],
            leader=True,
            config={"role-mapping": CONFIG_UNITS_ONLY},
        )
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
            config=CHARM_CONFIG,
        )
        state = ops.testing.State(
            relations=[relation],
            leader=True,
            config={"role-mapping": CONFIG_MACHINES_ONLY},
        )
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
            config=CHARM_CONFIG,
        )
        state = ops.testing.State(
            relations=[relation],
            leader=True,
            config={"role-mapping": CONFIG_MIXED},
        )
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
            config=CHARM_CONFIG,
        )
        state = ops.testing.State(
            relations=[relation],
            leader=False,
            config={"role-mapping": CONFIG_UNITS_ONLY},
        )
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
            config=CHARM_CONFIG,
        )
        state = ops.testing.State(
            relations=[relation],
            leader=True,
            config={"role-mapping": CONFIG_UNITS_ONLY},
        )
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
            config=CHARM_CONFIG,
        )
        state = ops.testing.State(
            relations=[relation],
            leader=True,
            config={"role-mapping": CONFIG_UNITS_ONLY},
        )
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
            config=CHARM_CONFIG,
        )
        state = ops.testing.State(
            relations=[relation],
            leader=True,
            config={"role-mapping": CONFIG_UNITS_ONLY},
        )
        out = ctx.run(ctx.on.leader_elected(), state)
        assert out.unit_status == ops.testing.ActiveStatus()
        out_rel = out.get_relation(relation.id)
        assert "assignments" in out_rel.local_app_data
