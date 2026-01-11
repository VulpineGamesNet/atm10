"""Configuration loader for Votifier service using environment variables."""

import os
from dataclasses import dataclass
from typing import Optional

from dotenv import load_dotenv


@dataclass
class RconConfig:
    """Minecraft RCON configuration."""

    host: str
    port: int
    password: str


@dataclass
class VotifierConfig:
    """Votifier server configuration."""

    host: str
    port: int
    keys_path: str


@dataclass
class Config:
    """Main configuration container."""

    rcon: RconConfig
    votifier: VotifierConfig
    debug: bool = False


def _get_env(key: str, default: Optional[str] = None, required: bool = False) -> Optional[str]:
    """Get environment variable with optional default and required validation."""
    value = os.getenv(key, default)
    if required and not value:
        raise ValueError(f"Required environment variable '{key}' is not set")
    return value


def _get_env_int(key: str, default: int) -> int:
    """Get environment variable as integer."""
    value = os.getenv(key)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        raise ValueError(f"Environment variable '{key}' must be an integer, got: {value}")


def _get_env_bool(key: str, default: bool) -> bool:
    """Get environment variable as boolean."""
    value = os.getenv(key)
    if value is None:
        return default
    return value.lower() in ("true", "1", "yes", "on")


def load_config(env_file: Optional[str] = ".env") -> Config:
    """
    Load configuration from environment variables.

    Args:
        env_file: Path to .env file (optional, defaults to ".env")

    Returns:
        Config object with all settings

    Raises:
        ValueError: If required config is missing or invalid
    """
    if env_file:
        load_dotenv(env_file)

    rcon_config = RconConfig(
        host=_get_env("RCON_HOST", "localhost"),
        port=_get_env_int("RCON_PORT", 25575),
        password=_get_env("RCON_PASSWORD", required=True),
    )

    votifier_config = VotifierConfig(
        host=_get_env("VOTIFIER_HOST", "0.0.0.0"),
        port=_get_env_int("VOTIFIER_PORT", 8192),
        keys_path=_get_env("KEYS_PATH", "keys"),
    )

    return Config(
        rcon=rcon_config,
        votifier=votifier_config,
        debug=_get_env_bool("DEBUG", False),
    )
