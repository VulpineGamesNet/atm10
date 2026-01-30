"""Tests for configuration loading."""

import os
import tempfile
from pathlib import Path

import pytest

from config import (
    Config,
    DatabaseConfig,
    DiscordConfig,
    MinecraftConfig,
    Settings,
    load_config,
    _get_env,
    _get_env_int,
)


class TestGetEnv:
    """Tests for _get_env helper function."""

    def test_get_env_returns_value(self, monkeypatch):
        """Test that _get_env returns the environment variable value."""
        monkeypatch.setenv("TEST_VAR", "test_value")
        assert _get_env("TEST_VAR") == "test_value"

    def test_get_env_returns_default(self, monkeypatch):
        """Test that _get_env returns default when variable not set."""
        monkeypatch.delenv("NONEXISTENT_VAR", raising=False)
        assert _get_env("NONEXISTENT_VAR", "default") == "default"

    def test_get_env_returns_none_without_default(self, monkeypatch):
        """Test that _get_env returns None when no default and not set."""
        monkeypatch.delenv("NONEXISTENT_VAR", raising=False)
        assert _get_env("NONEXISTENT_VAR") is None

    def test_get_env_required_raises(self, monkeypatch):
        """Test that _get_env raises ValueError when required and not set."""
        monkeypatch.delenv("REQUIRED_VAR", raising=False)
        with pytest.raises(ValueError, match="Required environment variable"):
            _get_env("REQUIRED_VAR", required=True)

    def test_get_env_required_with_value(self, monkeypatch):
        """Test that _get_env returns value when required and set."""
        monkeypatch.setenv("REQUIRED_VAR", "value")
        assert _get_env("REQUIRED_VAR", required=True) == "value"


class TestGetEnvInt:
    """Tests for _get_env_int helper function."""

    def test_get_env_int_returns_int(self, monkeypatch):
        """Test that _get_env_int parses integer correctly."""
        monkeypatch.setenv("INT_VAR", "42")
        assert _get_env_int("INT_VAR", 0) == 42

    def test_get_env_int_returns_default(self, monkeypatch):
        """Test that _get_env_int returns default when not set."""
        monkeypatch.delenv("INT_VAR", raising=False)
        assert _get_env_int("INT_VAR", 100) == 100

    def test_get_env_int_raises_on_invalid(self, monkeypatch):
        """Test that _get_env_int raises ValueError on non-integer."""
        monkeypatch.setenv("INT_VAR", "not_a_number")
        with pytest.raises(ValueError, match="must be an integer"):
            _get_env_int("INT_VAR", 0)


class TestLoadConfig:
    """Tests for load_config function."""

    def test_load_config_from_env(self, monkeypatch):
        """Test loading config from environment variables."""
        monkeypatch.setenv("DISCORD_TOKEN", "test_token")
        monkeypatch.setenv("DISCORD_CHANNEL_ID", "123456789")
        monkeypatch.setenv("DISCORD_GUILD_ID", "987654321")
        monkeypatch.setenv("RCON_HOST", "localhost")
        monkeypatch.setenv("RCON_PORT", "25575")
        monkeypatch.setenv("RCON_PASSWORD", "secret")
        monkeypatch.setenv("SERVER_NAME", "Test Server")

        config = load_config(env_file=None)

        assert config.discord.token == "test_token"
        assert config.discord.channel_id == 123456789
        assert config.discord.guild_id == 987654321
        assert config.minecraft.rcon_host == "localhost"
        assert config.minecraft.rcon_port == 25575
        assert config.minecraft.rcon_password == "secret"
        assert config.minecraft.server_name == "Test Server"

    def test_load_config_missing_token(self, monkeypatch):
        """Test that missing DISCORD_TOKEN raises ValueError."""
        monkeypatch.delenv("DISCORD_TOKEN", raising=False)
        monkeypatch.setenv("DISCORD_CHANNEL_ID", "123")
        monkeypatch.setenv("RCON_PASSWORD", "secret")

        with pytest.raises(ValueError, match="DISCORD_TOKEN"):
            load_config(env_file=None)

    def test_load_config_missing_channel_id(self, monkeypatch):
        """Test that missing DISCORD_CHANNEL_ID raises ValueError."""
        monkeypatch.setenv("DISCORD_TOKEN", "token")
        monkeypatch.delenv("DISCORD_CHANNEL_ID", raising=False)
        monkeypatch.setenv("RCON_PASSWORD", "secret")

        with pytest.raises(ValueError, match="DISCORD_CHANNEL_ID"):
            load_config(env_file=None)

    def test_load_config_missing_rcon_password(self, monkeypatch):
        """Test that missing RCON_PASSWORD raises ValueError."""
        monkeypatch.setenv("DISCORD_TOKEN", "token")
        monkeypatch.setenv("DISCORD_CHANNEL_ID", "123")
        monkeypatch.delenv("RCON_PASSWORD", raising=False)

        with pytest.raises(ValueError, match="RCON_PASSWORD"):
            load_config(env_file=None)

    def test_load_config_defaults(self, monkeypatch):
        """Test that defaults are applied correctly."""
        monkeypatch.setenv("DISCORD_TOKEN", "token")
        monkeypatch.setenv("DISCORD_CHANNEL_ID", "123")
        monkeypatch.setenv("RCON_PASSWORD", "secret")
        # Clear optional vars
        monkeypatch.delenv("DISCORD_GUILD_ID", raising=False)
        monkeypatch.delenv("RCON_HOST", raising=False)
        monkeypatch.delenv("RCON_PORT", raising=False)
        monkeypatch.delenv("SERVER_NAME", raising=False)
        monkeypatch.delenv("TOPIC_UPDATE_INTERVAL", raising=False)
        monkeypatch.delenv("STATS_CHECK_INTERVAL", raising=False)
        monkeypatch.delenv("MAX_MESSAGE_LENGTH", raising=False)
        monkeypatch.delenv("EVENTS_POLL_INTERVAL", raising=False)
        monkeypatch.delenv("DB_HOST", raising=False)
        monkeypatch.delenv("DB_PORT", raising=False)
        monkeypatch.delenv("DB_NAME", raising=False)
        monkeypatch.delenv("DB_USER", raising=False)
        monkeypatch.delenv("DB_PASSWORD", raising=False)

        config = load_config(env_file=None)

        assert config.discord.guild_id is None
        assert config.minecraft.rcon_host == "localhost"
        assert config.minecraft.rcon_port == 25575
        assert config.minecraft.server_name == "Minecraft Server"
        assert config.settings.topic_update_interval == 60
        assert config.settings.stats_check_interval == 5
        assert config.settings.max_message_length == 256
        assert config.settings.events_poll_interval == 2
        assert config.database.host == "localhost"
        assert config.database.port == 3306
        assert config.database.database == "minecraft"
        assert config.database.user == "root"
        assert config.database.password == ""

    def test_load_config_from_env_file(self, monkeypatch, tmp_path):
        """Test loading config from .env file."""
        # Clear any existing env vars
        for var in ["DISCORD_TOKEN", "DISCORD_CHANNEL_ID", "RCON_PASSWORD"]:
            monkeypatch.delenv(var, raising=False)

        # Create temp .env file
        env_file = tmp_path / ".env"
        env_file.write_text(
            "DISCORD_TOKEN=file_token\n"
            "DISCORD_CHANNEL_ID=111222333\n"
            "RCON_PASSWORD=file_secret\n"
        )

        config = load_config(env_file=str(env_file))

        assert config.discord.token == "file_token"
        assert config.discord.channel_id == 111222333
        assert config.minecraft.rcon_password == "file_secret"

    def test_load_config_settings_override(self, monkeypatch):
        """Test that settings can be overridden."""
        monkeypatch.setenv("DISCORD_TOKEN", "token")
        monkeypatch.setenv("DISCORD_CHANNEL_ID", "123")
        monkeypatch.setenv("RCON_PASSWORD", "secret")
        monkeypatch.setenv("TOPIC_UPDATE_INTERVAL", "120")
        monkeypatch.setenv("STATS_CHECK_INTERVAL", "10")
        monkeypatch.setenv("MAX_MESSAGE_LENGTH", "512")

        config = load_config(env_file=None)

        assert config.settings.topic_update_interval == 120
        assert config.settings.stats_check_interval == 10
        assert config.settings.max_message_length == 512


class TestDataclasses:
    """Tests for configuration dataclasses."""

    def test_discord_config(self):
        """Test DiscordConfig dataclass."""
        config = DiscordConfig(token="token", channel_id=123, guild_id=456)
        assert config.token == "token"
        assert config.channel_id == 123
        assert config.guild_id == 456

    def test_discord_config_optional_guild(self):
        """Test DiscordConfig with optional guild_id."""
        config = DiscordConfig(token="token", channel_id=123)
        assert config.guild_id is None

    def test_minecraft_config(self):
        """Test MinecraftConfig dataclass."""
        config = MinecraftConfig(
            rcon_host="host",
            rcon_port=25575,
            rcon_password="pass",
            server_name="Server",
        )
        assert config.rcon_host == "host"
        assert config.rcon_port == 25575
        assert config.rcon_password == "pass"
        assert config.server_name == "Server"

    def test_settings_defaults(self):
        """Test Settings dataclass defaults."""
        settings = Settings()
        assert settings.topic_update_interval == 60
        assert settings.stats_check_interval == 5
        assert settings.max_message_length == 256
        assert settings.events_poll_interval == 2

    def test_database_config_defaults(self):
        """Test DatabaseConfig dataclass defaults."""
        config = DatabaseConfig()
        assert config.host == "localhost"
        assert config.port == 3306
        assert config.database == "minecraft"
        assert config.user == "root"
        assert config.password == ""

    def test_database_config_async_url(self):
        """Test DatabaseConfig async_url property."""
        config = DatabaseConfig(
            host="db.example.com",
            port=3307,
            database="testdb",
            user="testuser",
            password="testpass",
        )
        expected = "mysql+asyncmy://testuser:testpass@db.example.com:3307/testdb"
        assert config.async_url == expected

    def test_database_config_async_url_empty_password(self):
        """Test DatabaseConfig async_url with empty password."""
        config = DatabaseConfig(host="localhost", user="root", password="")
        assert "root:@localhost" in config.async_url

    def test_config_container(self):
        """Test Config container dataclass."""
        discord = DiscordConfig(token="token", channel_id=123)
        minecraft = MinecraftConfig(
            rcon_host="host",
            rcon_port=25575,
            rcon_password="pass",
        )
        database = DatabaseConfig()
        settings = Settings()

        config = Config(discord=discord, minecraft=minecraft, database=database, settings=settings)

        assert config.discord.token == "token"
        assert config.minecraft.rcon_host == "host"
        assert config.database.host == "localhost"
        assert config.settings.topic_update_interval == 60
