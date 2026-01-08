"""
Discord-Minecraft Chat Sync Bot

Handles:
- Discord -> Minecraft chat relay via RCON
- Minecraft -> Discord chat relay via webhook (polling RCON /getstats)
- Channel topic updates with server stats (TPS, players, uptime)
- Server start/stop notifications (via RCON connectivity monitoring)
"""

import asyncio
import json
import logging
import re
import socket
import struct
from typing import Optional

import aiohttp
import discord
from discord.ext import commands, tasks

from config import Config, load_config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("discord_mc_bot")


class MinecraftBridge(commands.Cog):
    """Handles Minecraft <-> Discord communication."""

    EMBED_COLOR_GREEN = 0x57F287
    EMBED_COLOR_RED = 0xED4245
    EMBED_COLOR_ORANGE = 0xE67E22
    EMBED_COLOR_BLUE = 0x3498DB

    def __init__(self, bot: "DiscordMCBot", config: Config):
        self.bot = bot
        self.config = config
        self.last_stats: Optional[dict] = None
        self.rcon_lock = asyncio.Lock()
        self.last_topic: Optional[str] = None
        self.server_online: bool = False
        self.http_session: Optional[aiohttp.ClientSession] = None

    async def cog_load(self) -> None:
        """Called when cog is loaded."""
        self.http_session = aiohttp.ClientSession()
        self.poll_server_stats.start()
        self.update_channel_topic.start()
        logger.info("MinecraftBridge cog loaded")

    async def cog_unload(self) -> None:
        """Called when cog is unloaded."""
        self.poll_server_stats.cancel()
        self.update_channel_topic.cancel()
        if self.http_session:
            await self.http_session.close()

    def _rcon_sync(self, command: str) -> str:
        """Synchronous RCON command execution using raw sockets."""
        SERVERDATA_AUTH = 3
        SERVERDATA_EXECCOMMAND = 2

        def send_packet(
            sock: socket.socket, packet_id: int, packet_type: int, payload: str
        ) -> None:
            """Send an RCON packet."""
            payload_bytes = payload.encode("utf-8") + b"\x00\x00"
            packet = struct.pack("<ii", packet_id, packet_type) + payload_bytes
            packet = struct.pack("<i", len(packet)) + packet
            sock.sendall(packet)

        def recv_packet(sock: socket.socket) -> tuple[int, int, str]:
            """Receive an RCON packet."""
            length_data = sock.recv(4)
            if len(length_data) < 4:
                raise ConnectionError("Failed to read packet length")
            length = struct.unpack("<i", length_data)[0]

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
            sock.connect(
                (self.config.minecraft.rcon_host, self.config.minecraft.rcon_port)
            )

            send_packet(sock, 1, SERVERDATA_AUTH, self.config.minecraft.rcon_password)
            packet_id, packet_type, _ = recv_packet(sock)

            if packet_id == -1:
                raise ConnectionError("RCON authentication failed")

            send_packet(sock, 2, SERVERDATA_EXECCOMMAND, command)
            _, _, response = recv_packet(sock)

            return response

        finally:
            sock.close()

    async def send_rcon_command(self, command: str) -> Optional[str]:
        """Send a command to Minecraft server via RCON."""
        async with self.rcon_lock:
            try:
                loop = asyncio.get_event_loop()
                result = await loop.run_in_executor(None, self._rcon_sync, command)
                return result
            except Exception as e:
                logger.debug(f"RCON error: {e}")
                return None

    async def get_stats_via_rcon(self) -> Optional[dict]:
        """Get server stats via RCON /getstats command."""
        response = await self.send_rcon_command("getstats")
        if response is None:
            return None

        try:
            return json.loads(response)
        except json.JSONDecodeError as e:
            logger.warning(f"Invalid JSON from /getstats: {e}")
            return None

    async def send_webhook_message(
        self,
        content: str,
        username: Optional[str] = None,
        avatar_url: Optional[str] = None,
    ) -> bool:
        """Send a message via Discord webhook."""
        if not self.config.discord.webhook_url:
            logger.debug("Webhook URL not configured")
            return False

        if not self.http_session:
            return False

        payload = {"content": content}
        if username:
            payload["username"] = username
        if avatar_url:
            payload["avatar_url"] = avatar_url

        try:
            async with self.http_session.post(
                self.config.discord.webhook_url,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status in (200, 204):
                    return True
                elif resp.status == 429:
                    logger.warning("Webhook rate limited")
                    return False
                else:
                    logger.warning(f"Webhook returned status: {resp.status}")
                    return False
        except Exception as e:
            logger.error(f"Webhook error: {e}")
            return False

    async def send_webhook_embed(
        self,
        description: str,
        color: int,
        thumbnail_url: Optional[str] = None,
    ) -> bool:
        """Send an embed via Discord webhook."""
        if not self.config.discord.webhook_url:
            logger.debug("Webhook URL not configured")
            return False

        if not self.http_session:
            return False

        embed = {"description": description, "color": color}
        if thumbnail_url:
            embed["thumbnail"] = {"url": thumbnail_url}

        payload = {"embeds": [embed]}

        try:
            async with self.http_session.post(
                self.config.discord.webhook_url,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status in (200, 204):
                    return True
                elif resp.status == 429:
                    logger.warning("Webhook rate limited")
                    return False
                else:
                    logger.warning(f"Webhook returned status: {resp.status}")
                    return False
        except Exception as e:
            logger.error(f"Webhook embed error: {e}")
            return False

    async def process_messages(self, messages: list) -> None:
        """Process messages from KubeJS (chat, join, leave)."""
        for msg in messages:
            msg_type = msg.get("type")
            player = msg.get("player", "Unknown")
            uuid = msg.get("uuid", "")

            if msg_type == "chat":
                content = msg.get("message", "")
                avatar_url = f"https://crafatar.com/avatars/{uuid}?size=128&overlay"
                await self.send_webhook_message(content, player, avatar_url)
                logger.info(f"Relayed chat from {player}: {content[:50]}...")

            elif msg_type == "join":
                icon_url = f"https://crafatar.com/avatars/{uuid}?size=64&overlay"
                await self.send_webhook_embed(
                    f":green_circle: **{player}** logged in",
                    self.EMBED_COLOR_GREEN,
                    icon_url,
                )
                logger.info(f"Sent join notification for {player}")

            elif msg_type == "leave":
                icon_url = f"https://crafatar.com/avatars/{uuid}?size=64&overlay"
                await self.send_webhook_embed(
                    f":red_circle: **{player}** logged out",
                    self.EMBED_COLOR_RED,
                    icon_url,
                )
                logger.info(f"Sent leave notification for {player}")

    @tasks.loop(seconds=2)
    async def poll_server_stats(self) -> None:
        """Poll server stats via RCON and process messages."""
        stats = await self.get_stats_via_rcon()

        was_online = self.server_online

        if stats:
            self.last_stats = stats
            self.server_online = True

            if not was_online:
                server_name = self.config.minecraft.server_name
                await self.send_webhook_embed(
                    f":white_check_mark: **{server_name}** is now online!",
                    self.EMBED_COLOR_BLUE,
                )
                logger.info("Server came online - sent notification")

            messages = stats.get("messages", [])
            if messages:
                await self.process_messages(messages)
        else:
            self.server_online = False

            if was_online:
                server_name = self.config.minecraft.server_name
                await self.send_webhook_embed(
                    f":octagonal_sign: **{server_name}** is restarting...",
                    self.EMBED_COLOR_ORANGE,
                )
                logger.info("Server went offline - sent notification")

    @poll_server_stats.before_loop
    async def before_poll_stats(self) -> None:
        await self.bot.wait_until_ready()

    def sanitize_discord_message(self, content: str) -> str:
        """Sanitize Discord message for Minecraft."""
        content = re.sub(r"<@!?(\d+)>", "[mention]", content)
        content = re.sub(r"<#(\d+)>", "[channel]", content)
        content = re.sub(r"<@&(\d+)>", "[role]", content)
        content = re.sub(r"<a?:(\w+):\d+>", r":\1:", content)
        content = content.replace('"', "'")
        content = content.replace("\\", "")
        content = content.replace("\n", " ").replace("\r", " ")
        content = re.sub(r"\s+", " ", content).strip()

        max_len = self.config.settings.max_message_length
        if len(content) > max_len:
            content = content[: max_len - 3] + "..."

        return content

    def sanitize_username(self, username: str) -> str:
        """Sanitize Discord username for Minecraft command."""
        username = re.sub(r"[^\w\s\-_]", "", username)
        username = username[:16]
        username = username.strip()
        if not username:
            username = "Discord"
        return username

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        """Handle Discord messages and relay to Minecraft."""
        if message.author.bot:
            return

        if message.channel.id != self.config.discord.channel_id:
            return

        content = message.content
        if not content:
            if message.attachments:
                content = "[attachment]"
            elif message.stickers:
                content = "[sticker]"
            else:
                return

        content = self.sanitize_discord_message(content)
        if not content:
            return

        username = self.sanitize_username(message.author.display_name)
        command = f'discordmsg "{username}" {content}'

        logger.info(f"Relaying message from {username}: {content[:50]}...")

        result = await self.send_rcon_command(command)
        if result is None:
            logger.warning(f"Failed to relay message from {username}")
            try:
                embed = discord.Embed(
                    description=f"**Message was not delivered**\n> {message.content}",
                    color=0xED4245,  # Red
                )
                await message.reply(embed=embed, mention_author=False)
            except discord.Forbidden:
                pass

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

            tps = self.last_stats.get("tps", 20.0)
            player_count = self.last_stats.get("playerCount", 0)
            uptime = self.last_stats.get("uptime", "0h 0m")

            topic = f"TPS: {tps:.2f} | Players: {player_count} | Uptime: {uptime}"

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

        activity = discord.Activity(
            type=discord.ActivityType.watching,
            name=self.config.minecraft.server_name,
        )
        await self.change_presence(activity=activity)


def main() -> None:
    """Main entry point."""
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
    logger.info(f"Webhook configured: {'Yes' if config.discord.webhook_url else 'No'}")

    bot = DiscordMCBot(config)

    try:
        bot.run(config.discord.token)
    except discord.LoginFailure:
        logger.error("Invalid Discord token")
    except Exception as e:
        logger.error(f"Bot crashed: {e}")


if __name__ == "__main__":
    main()
