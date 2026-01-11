"""Shared pytest fixtures for Votifier service tests."""

import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from config import Config, RconConfig, VotifierConfig
from votifier_protocol import VotifierProtocol


@pytest.fixture
def temp_keys_dir():
    """Create a temporary directory for RSA keys."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.fixture
def votifier_protocol(temp_keys_dir):
    """Create a VotifierProtocol instance with temporary keys."""
    return VotifierProtocol(temp_keys_dir)


@pytest.fixture
def sample_vote_data():
    """Sample decrypted vote data."""
    return b"VOTE\nPlanetMinecraft\nTestPlayer\n192.168.1.1\n1234567890\n"


@pytest.fixture
def rcon_config():
    """Sample RCON configuration."""
    return RconConfig(
        host="localhost",
        port=25575,
        password="test_password",
    )


@pytest.fixture
def votifier_config(temp_keys_dir):
    """Sample Votifier configuration."""
    return VotifierConfig(
        host="0.0.0.0",
        port=8192,
        keys_path=temp_keys_dir,
    )


@pytest.fixture
def full_config(rcon_config, votifier_config):
    """Complete configuration object."""
    return Config(
        rcon=rcon_config,
        votifier=votifier_config,
        debug=False,
    )


@pytest.fixture
def env_vars():
    """Set up test environment variables."""
    original_env = os.environ.copy()

    os.environ["RCON_HOST"] = "test-host"
    os.environ["RCON_PORT"] = "25575"
    os.environ["RCON_PASSWORD"] = "test-password"
    os.environ["VOTIFIER_HOST"] = "0.0.0.0"
    os.environ["VOTIFIER_PORT"] = "8192"
    os.environ["KEYS_PATH"] = "test-keys"
    os.environ["DEBUG"] = "false"

    yield

    os.environ.clear()
    os.environ.update(original_env)


@pytest.fixture
def mock_mcrcon(mocker):
    """Mock the MCRcon class."""
    mock_mcr = MagicMock()
    mock_mcr.__enter__ = MagicMock(return_value=mock_mcr)
    mock_mcr.__exit__ = MagicMock(return_value=False)
    mock_mcr.command = MagicMock(return_value="Command executed")

    mock_class = mocker.patch("rcon_client.MCRcon", return_value=mock_mcr)
    return mock_class, mock_mcr
