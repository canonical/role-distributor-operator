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
def charm():
    """Return the path of the .charm file under test."""
    if "CHARM_PATH" in os.environ:
        charm_path = pathlib.Path(os.environ["CHARM_PATH"])
        if not charm_path.exists():
            raise FileNotFoundError(f"Charm does not exist: {charm_path}")
        return charm_path
    return next(pathlib.Path(".").glob("*.charm"))


@pytest.fixture(scope="session")
def dummy_charm():
    """Return the path of the dummy-requirer .charm file."""
    if "DUMMY_CHARM_PATH" in os.environ:
        charm_path = pathlib.Path(os.environ["DUMMY_CHARM_PATH"])
        if not charm_path.exists():
            raise FileNotFoundError(f"Dummy charm does not exist: {charm_path}")
        return charm_path
    return next(pathlib.Path("tests/integration/charms/dummy-requirer").glob("*.charm"))


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
