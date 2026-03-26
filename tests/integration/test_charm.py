"""Integration tests for role-distributor charm."""

from __future__ import annotations

import pathlib

import jubilant


def test_deploy_blocked_without_config(charm: pathlib.Path, juju: jubilant.Juju):
    """Deploy the charm. Without config it should reach blocked status."""
    juju.deploy(f"./{charm}")
    juju.wait(lambda status: jubilant.all_blocked(status, "role-distributor"))


def test_config_without_relations_sets_waiting(juju: jubilant.Juju):
    """Valid config but no relations -> WaitingStatus (unmatched models)."""
    model_name = juju.status().model.name
    config = f"""
{model_name}:
  role-distributor/0:
    roles: [control]
"""
    juju.config("role-distributor", {"role-mapping": config})
    juju.wait(lambda s: jubilant.all_waiting(s, "role-distributor"))
