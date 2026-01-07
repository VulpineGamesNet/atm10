"""
Discord-Minecraft Chat Sync Bot

Handles:
- Discord -> Minecraft chat relay via RCON
- Channel topic updates with server stats (TPS, players, uptime)
"""

import asyncio
import json
import logging
import re
import struct
import socket
from pathlib import Path
from typing import Optional

import discord
from discord.ext import commands, tasks

from config import load_config, Config

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
    ]
)
logger = logging.getLogger("discord_mc_bot")


class MinecraftBridge(commands.Cog):
    """Handles Minecraft <-> Discord communication."""

    def __init__(self, bot: "DiscordMCBot", config: Config):
        self.bot = bot
        self.config = config
        self.last_stats: Optional[dict] = None
        self.rcon_lock = asyncio.Lock()
        self.last_topic: Optional[str] = None

    async def cog_load(self) -> None:
        """Called when cog is loaded."""
        self.update_channel_topic.start()
        self.read_server_stats.start()
        logger.info("MinecraftBridge cog loaded")

    async def cog_unload(self) -> None:
        """Called when cog is unloaded."""
        self.update_channel_topic.cancel()
        self.read_server_stats.cancel()

    async def send_rcon_command(self, command: str) -> Optional[str]:
        """Send a command to Minecraft server via RCON."""
        async with self.rcon_lock:
            try:
                loop = asyncio.get_event_loop()
                result = await loop.run_in_executor(None, self._rcon_sync, command)
                return result
            except Exception as e:
                logger.error(f"RCON error: {e}")
                return None

    def _rcon_sync(self, command: str) -> str:
        """Synchronous RCON command execution using raw sockets."""
        SERVERDATA_AUTH = 3
        SERVERDATA_AUTH_RESPONSE = 2
        SERVERDATA_EXECCOMMAND = 2
        SERVERDATA_RESPONSE_VALUE = 0

        def send_packet(sock: socket.socket, packet_id: int, packet_type: int, payload: str) -> None:
            """Send an RCON packet."""
            payload_bytes = payload.encode("utf-8") + b"\x00\x00"
            packet = struct.pack("<ii", packet_id, packet_type) + payload_bytes
            packet = struct.pack("<i", len(packet)) + packet
            sock.sendall(packet)

        def recv_packet(sock: socket.socket) -> tuple[int, int, str]:
            """Receive an RCON packet."""
            # Read packet length
            length_data = sock.recv(4)
            if len(length_data) < 4:
                raise ConnectionError("Failed to read packet length")
            length = struct.unpack("<i", length_data)[0]

            # Read packet data
            data = b""
            while len(data) < length:
                chunk = sock.recv(length - len(data))
                if not chunk:
                    raise ConnectionError("Connection closed")
                data += chunk

            packet_id = struct.unpack("<i", data[0:4])[0]
            packet_type = struct.unpack("<i", data[4:8])[0]
            payload = data[8:-2].decode("utf-8")

            return packet_id, packet_type, payload

        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5.0)

        try:
            sock.connect((self.config.minecraft.rcon_host, self.config.minecraft.rcon_port))

            # Authenticate
            send_packet(sock, 1, SERVERDATA_AUTH, self.config.minecraft.rcon_password)
            packet_id, packet_type, _ = recv_packet(sock)

            if packet_id == -1:
                raise ConnectionError("RCON authentication failed")

            # Send command
            send_packet(sock, 2, SERVERDATA_EXECCOMMAND, command)
            _, _, response = recv_packet(sock)

            return response

        finally:
            sock.close()

    def read_stats_file(self) -> Optional[dict]:
        """Read server stats from file written by KubeJS."""
        try:
            stats_path = Path(self.config.minecraft.stats_file)
            if not stats_path.exists():
                logger.debug(f"Stats file not found: {stats_path}")
                return None

            with open(stats_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except json.JSONDecodeError as e:
            logger.warning(f"Invalid JSON in stats file: {e}")
            return None
        except Exception as e:
            logger.warning(f"Could not read stats file: {e}")
            return None

    def sanitize_discord_message(self, content: str) -> str:
        """
        Sanitize Discord message for Minecraft.
        - Remove/escape special characters
        - Truncate to max length
        - Remove Discord formatting
        """
        # Remove Discord mentions (convert to text)
        content = re.sub(r"<@!?(\d+)>", "[mention]", content)
        content = re.sub(r"<#(\d+)>", "[channel]", content)
        content = re.sub(r"<@&(\d+)>", "[role]", content)

        # Remove custom emojis (keep name)
        content = re.sub(r"<a?:(\w+):\d+>", r":\1:", content)

        # Remove markdown formatting that might break MC
        content = content.replace('"', "'")
        content = content.replace("\\", "")

        # Remove newlines (replace with space)
        content = content.replace("\n", " ").replace("\r", " ")

        # Remove multiple spaces
        content = re.sub(r"\s+", " ", content).strip()

        # Truncate
        max_len = self.config.settings.max_message_length
        if len(content) > max_len:
            content = content[: max_len - 3] + "..."

        return content

    def sanitize_username(self, username: str) -> str:
        """Sanitize Discord username for Minecraft command."""
        # Remove special characters, keep alphanumeric, spaces, dashes, underscores
        username = re.sub(r"[^\w\s\-_]", "", username)
        # Limit length
        username = username[:16]
        # Remove leading/trailing whitespace
        username = username.strip()
        # Default if empty
        if not username:
            username = "Discord"
        return username

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        """Handle Discord messages and relay to Minecraft."""
        # Ignore bots
        if message.author.bot:
            return

        # Only process messages in the configured channel
        if message.channel.id != self.config.discord.channel_id:
            return

        # Get message content
        content = message.content
        if not content:
            # Handle attachment-only messages
            if message.attachments:
                content = "[attachment]"
            elif message.stickers:
                content = "[sticker]"
            else:
                return

        # Sanitize for Minecraft
        content = self.sanitize_discord_message(content)
        if not content:
            return

        # Get username (nickname or display name)
        username = self.sanitize_username(message.author.display_name)

        # Send to Minecraft via RCON
        # Escape content for command line
        # The KubeJS script has /discordmsg <username> <message>
        command = f'discordmsg "{username}" {content}'

        logger.info(f"Relaying message from {username}: {content[:50]}...")

        result = await self.send_rcon_command(command)
        if result is None:
            logger.warning(f"Failed to relay message from {username}")
            # Add reaction to indicate failure
            try:
                await message.add_reaction("\u274c")  # X emoji
            except discord.Forbidden:
                pass
        else:
            # Add checkmark reaction on success (optional)
            try:
                await message.add_reaction("\u2705")  # Checkmark emoji
            except discord.Forbidden:
                pass

    @tasks.loop(seconds=5)
    async def read_server_stats(self) -> None:
        """Periodically read server stats from file."""
        stats = self.read_stats_file()
        if stats:
            self.last_stats = stats

    @read_server_stats.before_loop
    async def before_read_stats(self) -> None:
        await self.bot.wait_until_ready()

    @tasks.loop(seconds=60)
    async def update_channel_topic(self) -> None:
        """Update Discord channel topic with server stats."""
        if not self.last_stats:
            logger.debug("No stats available for topic update")
            return

        try:
            channel = self.bot.get_channel(self.config.discord.channel_id)
            if not channel:
                logger.warning("Could not find configured channel")
                return

            if not isinstance(channel, discord.TextChannel):
                logger.warning("Configured channel is not a text channel")
                return

            # Build topic string
            # Format: "TPS: 20.00 | Players: 42 | Uptime: 21h 1m"
            tps = self.last_stats.get("tps", 20.0)
            player_count = self.last_stats.get("playerCount", 0)
            uptime = self.last_stats.get("uptime", "0h 0m")

            topic = f"TPS: {tps:.2f} | Players: {player_count} | Uptime: {uptime}"

            # Only update if topic changed (to avoid rate limits)
            if self.last_topic == topic:
                return

            await channel.edit(topic=topic)
            self.last_topic = topic
            logger.info(f"Updated channel topic: {topic}")

        except discord.Forbidden:
            logger.error("Bot lacks permission to edit channel topic")
        except discord.HTTPException as e:
            if e.status == 429:
                logger.warning("Rate limited when updating channel topic")
            else:
                logger.error(f"HTTP error updating channel topic: {e}")
        except Exception as e:
            logger.error(f"Error updating channel topic: {e}")

    @update_channel_topic.before_loop
    async def before_update_topic(self) -> None:
        await self.bot.wait_until_ready()


class DiscordMCBot(commands.Bot):
    """Main bot class."""

    def __init__(self, config: Config):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.guilds = True

        super().__init__(
            command_prefix="!mc",
            intents=intents,
            help_command=None,
        )

        self.config = config

    async def setup_hook(self) -> None:
        """Called when bot is starting up."""
        await self.add_cog(MinecraftBridge(self, self.config))
        logger.info("Bot setup complete")

    async def on_ready(self) -> None:
        """Called when bot is connected and ready."""
        logger.info(f"Logged in as {self.user.name} ({self.user.id})")
        logger.info(f"Monitoring channel ID: {self.config.discord.channel_id}")

        # Set bot status
        activity = discord.Activity(
            type=discord.ActivityType.watching,
            name=self.config.minecraft.server_name,
        )
        await self.change_presence(activity=activity)


def main() -> None:
    """Main entry point."""
    # Load configuration from environment variables / .env file
    logger.info("Loading configuration from environment...")

    try:
        config = load_config()
    except ValueError as e:
        logger.error(f"Configuration error: {e}")
        logger.error("Please copy .env.example to .env and fill in your values")
        return
    except Exception as e:
        logger.error(f"Failed to load config: {e}")
        return

    logger.info(f"RCON host: {config.minecraft.rcon_host}:{config.minecraft.rcon_port}")
    logger.info(f"Stats file: {config.minecraft.stats_file}")

    # Create and run bot
    bot = DiscordMCBot(config)

    try:
        bot.run(config.discord.token)
    except discord.LoginFailure:
        logger.error("Invalid Discord token")
    except Exception as e:
        logger.error(f"Bot crashed: {e}")


if __name__ == "__main__":
    main()
