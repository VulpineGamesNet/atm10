"""Configuration loader for Discord-Minecraft chat sync bot using environment variables."""

import os
from dataclasses import dataclass, field
from typing import Optional

from dotenv import load_dotenv


@dataclass
class DiscordConfig:
    """Discord-related configuration."""

    token: str
    channel_id: int
    guild_id: Optional[int] = None


@dataclass
class MinecraftConfig:
    """Minecraft server configuration."""

    rcon_host: str
    rcon_port: int
    rcon_password: str
    stats_file: str
    server_name: str = "Minecraft Server"


@dataclass
class Settings:
    """General bot settings."""

    topic_update_interval: int = 60  # seconds
    stats_check_interval: int = 5  # seconds
    max_message_length: int = 256


@dataclass
class Config:
    """Main configuration container."""

    discord: DiscordConfig
    minecraft: MinecraftConfig
    settings: Settings = field(default_factory=Settings)


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


def load_config(env_file: Optional[str] = ".env") -> Config:
    """
    Load configuration from environment variables.

    Looks for a .env file in the current directory or at the path specified.
    Environment variables take precedence over .env file values.

    Args:
        env_file: Path to .env file (optional, defaults to ".env")

    Returns:
        Config object with all settings

    Raises:
        ValueError: If required config is missing or invalid
    """
    # Load .env file if it exists
    if env_file:
        load_dotenv(env_file)

    # Parse Discord config
    discord_config = DiscordConfig(
        token=_get_env("DISCORD_TOKEN", required=True),
        channel_id=_get_env_int("DISCORD_CHANNEL_ID", 0),
        guild_id=_get_env_int("DISCORD_GUILD_ID", 0) or None,
    )

    if not discord_config.channel_id:
        raise ValueError("DISCORD_CHANNEL_ID must be set")

    # Parse Minecraft config
    minecraft_config = MinecraftConfig(
        rcon_host=_get_env("RCON_HOST", "localhost"),
        rcon_port=_get_env_int("RCON_PORT", 25575),
        rcon_password=_get_env("RCON_PASSWORD", required=True),
        stats_file=_get_env("STATS_FILE", "/app/server_data/server_stats.json"),
        server_name=_get_env("SERVER_NAME", "Minecraft Server"),
    )

    # Parse settings (all optional with defaults)
    settings = Settings(
        topic_update_interval=_get_env_int("TOPIC_UPDATE_INTERVAL", 60),
        stats_check_interval=_get_env_int("STATS_CHECK_INTERVAL", 5),
        max_message_length=_get_env_int("MAX_MESSAGE_LENGTH", 256),
    )

    return Config(
        discord=discord_config,
        minecraft=minecraft_config,
        settings=settings,
    )
