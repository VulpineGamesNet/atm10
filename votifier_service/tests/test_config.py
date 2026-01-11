"""Tests for configuration loading."""

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from config import (
    Config,
    RconConfig,
    VotifierConfig,
    _get_env,
    _get_env_bool,
    _get_env_int,
    load_config,
)


class TestGetEnv:
    """Tests for _get_env helper function."""

    def test_returns_value_when_set(self, monkeypatch):
        monkeypatch.setenv("TEST_VAR", "test_value")
        assert _get_env("TEST_VAR") == "test_value"

    def test_returns_default_when_not_set(self):
        assert _get_env("NONEXISTENT_VAR", "default") == "default"

    def test_returns_none_when_not_set_no_default(self):
        assert _get_env("NONEXISTENT_VAR") is None

    def test_raises_when_required_and_not_set(self):
        with pytest.raises(ValueError, match="Required environment variable"):
            _get_env("NONEXISTENT_VAR", required=True)

    def test_returns_value_when_required_and_set(self, monkeypatch):
        monkeypatch.setenv("REQUIRED_VAR", "value")
        assert _get_env("REQUIRED_VAR", required=True) == "value"


class TestGetEnvInt:
    """Tests for _get_env_int helper function."""

    def test_returns_int_when_valid(self, monkeypatch):
        monkeypatch.setenv("INT_VAR", "42")
        assert _get_env_int("INT_VAR", 0) == 42

    def test_returns_default_when_not_set(self):
        assert _get_env_int("NONEXISTENT_VAR", 100) == 100

    def test_raises_when_not_integer(self, monkeypatch):
        monkeypatch.setenv("INVALID_INT", "not_a_number")
        with pytest.raises(ValueError, match="must be an integer"):
            _get_env_int("INVALID_INT", 0)


class TestGetEnvBool:
    """Tests for _get_env_bool helper function."""

    @pytest.mark.parametrize("value", ["true", "True", "TRUE", "1", "yes", "on"])
    def test_returns_true_for_truthy_values(self, monkeypatch, value):
        monkeypatch.setenv("BOOL_VAR", value)
        assert _get_env_bool("BOOL_VAR", False) is True

    @pytest.mark.parametrize("value", ["false", "False", "0", "no", "off", "anything"])
    def test_returns_false_for_falsy_values(self, monkeypatch, value):
        monkeypatch.setenv("BOOL_VAR", value)
        assert _get_env_bool("BOOL_VAR", True) is False

    def test_returns_default_when_not_set(self):
        assert _get_env_bool("NONEXISTENT_VAR", True) is True
        assert _get_env_bool("NONEXISTENT_VAR", False) is False


class TestRconConfig:
    """Tests for RconConfig dataclass."""

    def test_create_config(self):
        config = RconConfig(host="localhost", port=25575, password="secret")
        assert config.host == "localhost"
        assert config.port == 25575
        assert config.password == "secret"


class TestVotifierConfig:
    """Tests for VotifierConfig dataclass."""

    def test_create_config(self):
        config = VotifierConfig(host="0.0.0.0", port=8192, keys_path="/app/keys")
        assert config.host == "0.0.0.0"
        assert config.port == 8192
        assert config.keys_path == "/app/keys"


class TestConfig:
    """Tests for main Config dataclass."""

    def test_create_config(self, rcon_config, votifier_config):
        config = Config(rcon=rcon_config, votifier=votifier_config)
        assert config.rcon == rcon_config
        assert config.votifier == votifier_config
        assert config.debug is False

    def test_create_config_with_debug(self, rcon_config, votifier_config):
        config = Config(rcon=rcon_config, votifier=votifier_config, debug=True)
        assert config.debug is True


class TestLoadConfig:
    """Tests for load_config function."""

    def test_load_config_with_env_vars(self, env_vars):
        config = load_config(env_file=None)

        assert config.rcon.host == "test-host"
        assert config.rcon.port == 25575
        assert config.rcon.password == "test-password"
        assert config.votifier.host == "0.0.0.0"
        assert config.votifier.port == 8192
        assert config.votifier.keys_path == "test-keys"
        assert config.debug is False

    def test_load_config_missing_password(self, monkeypatch):
        monkeypatch.delenv("RCON_PASSWORD", raising=False)
        with pytest.raises(ValueError, match="RCON_PASSWORD"):
            load_config(env_file=None)

    def test_load_config_defaults(self, monkeypatch):
        monkeypatch.setenv("RCON_PASSWORD", "password")
        config = load_config(env_file=None)

        assert config.rcon.host == "localhost"
        assert config.rcon.port == 25575
        assert config.votifier.host == "0.0.0.0"
        assert config.votifier.port == 8192
        assert config.votifier.keys_path == "keys"

    def test_load_config_debug_enabled(self, monkeypatch):
        monkeypatch.setenv("RCON_PASSWORD", "password")
        monkeypatch.setenv("DEBUG", "true")
        config = load_config(env_file=None)

        assert config.debug is True
