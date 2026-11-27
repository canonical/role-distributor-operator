"""Integration test fixtures for role-distributor charm."""

import logging
import os
import pathlib
import sys
import time

import jubilant
import pytest

logger = logging.getLogger(__name__)


@pytest.fixture(scope="module")
def juju(request: pytest.FixtureRequest):
    """Create a temporary Juju model for running tests."""
    with jubilant.temp_model() as juju:
        yield juju
        if request.session.testsfailed:
            logger.info("Collecting Juju logs...")
            time.sleep(0.5)
            log = juju.debug_log(limit=1000)
            print(log, end="", file=sys.stderr)


@pytest.fixture(scope="session")
def base() -> str:
    """Return the ubuntu base under test, e.g. 'ubuntu@24.04'."""
    return os.environ.get("TEST_BASE", "ubuntu@24.04")


def _charm_artifact(root: pathlib.Path, base: str) -> pathlib.Path:
    """Return the .charm artifact matching the base channel."""
    token = base
    matches = list(root.glob(f"*{token}*.charm"))
    if not matches:
        raise FileNotFoundError(f"No .charm artifact found for {base} in {root}")
    return matches[0]


@pytest.fixture(scope="session")
def charm(base: str):
    """Return the path of the .charm file under test."""
    if "CHARM_PATH" in os.environ:
        charm_path = pathlib.Path(os.environ["CHARM_PATH"])
        if not charm_path.exists():
            raise FileNotFoundError(f"Charm does not exist: {charm_path}")
        return charm_path
    return _charm_artifact(pathlib.Path("."), base)


@pytest.fixture(scope="session")
def dummy_charm(base: str):
    """Return the path of the dummy-requirer .charm file."""
    if "DUMMY_CHARM_PATH" in os.environ:
        charm_path = pathlib.Path(os.environ["DUMMY_CHARM_PATH"])
        if not charm_path.exists():
            raise FileNotFoundError(f"Dummy charm does not exist: {charm_path}")
        return charm_path
    return _charm_artifact(pathlib.Path("tests/integration/charms/dummy-requirer"), base)


@pytest.fixture(scope="module")
def provider_model(request: pytest.FixtureRequest):
    """Create a temporary Juju model for the role-distributor (provider)."""
    with jubilant.temp_model() as juju:
        yield juju
        if request.session.testsfailed:
            logger.info("Collecting provider model Juju logs...")
            time.sleep(0.5)
            log = juju.debug_log(limit=1000)
            print(log, end="", file=sys.stderr)


@pytest.fixture(scope="module")
def requirer_model(request: pytest.FixtureRequest):
    """Create a temporary Juju model for the dummy-requirer apps."""
    with jubilant.temp_model() as juju:
        yield juju
        if request.session.testsfailed:
            logger.info("Collecting requirer model Juju logs...")
            time.sleep(0.5)
            log = juju.debug_log(limit=1000)
            print(log, end="", file=sys.stderr)
