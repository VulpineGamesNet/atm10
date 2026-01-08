"""
Discord-Minecraft Chat Sync Bot

Handles:
- Discord -> Minecraft chat relay via RCON
- Minecraft -> Discord chat relay via webhook (polling RCON /getstats)
- Channel topic updates with server stats (TPS, players, uptime)
- Server start/stop notifications (via RCON connectivity monitoring)
"""

import asyncio
import io
import json
import logging
import re
import signal
import socket
import struct
import time
from typing import Optional

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands, tasks
from PIL import Image

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
    EMBED_COLOR_PURPLE = 0x9B59B6  # For bot status notifications
    SERVER_ICON_URL = "https://raw.githubusercontent.com/VulpineGamesNet/atm10/main/discord_bot/resources/vulpines.png"
    BOT_ICON_URL = "https://raw.githubusercontent.com/VulpineGamesNet/atm10/main/discord_bot/resources/vulpines.png"

    # Debounce settings for status notifications
    STATUS_COOLDOWN: int = 30  # seconds between status notifications
    OFFLINE_THRESHOLD: int = 3  # consecutive failed checks before "offline"

    WEBHOOK_NAME = "Minecraft Bridge"

    RCON_SERVERDATA_AUTH = 3
    RCON_SERVERDATA_EXECCOMMAND = 2

    def __init__(self, bot: "DiscordMCBot", config: Config):
        self.bot = bot
        self.config = config
        self.last_stats: Optional[dict] = None
        self.rcon_lock = asyncio.Lock()
        self.last_topic: Optional[str] = None
        self.server_online: bool = False
        self.http_session: Optional[aiohttp.ClientSession] = None
        self.managed_webhook: Optional[discord.Webhook] = None
        # Debounce state
        self.last_status_notification: float = 0
        self.consecutive_offline_checks: int = 0
        # Persistent RCON connection state
        self._rcon_socket: Optional[socket.socket] = None
        self._rcon_connected: bool = False

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
        self._rcon_disconnect()

    async def setup_webhook(self) -> None:
        """Get or create a webhook for the configured channel."""
        # Skip if manual webhook URL is configured
        if self.config.discord.webhook_url:
            logger.info("Using manually configured webhook URL")
            return

        channel = self.bot.get_channel(self.config.discord.channel_id)
        if not channel or not isinstance(channel, discord.TextChannel):
            logger.warning("Could not find text channel for webhook setup")
            return

        try:
            webhooks = await channel.webhooks()
            # Look for existing webhook created by this bot
            for webhook in webhooks:
                if webhook.name == self.WEBHOOK_NAME:
                    self.managed_webhook = webhook
                    logger.info(f"Found existing webhook: {webhook.name}")
                    return

            # Create new webhook
            self.managed_webhook = await channel.create_webhook(
                name=self.WEBHOOK_NAME,
                reason="Minecraft chat bridge webhook",
            )
            logger.info(f"Created new webhook: {self.managed_webhook.name}")

        except discord.Forbidden:
            logger.warning("Missing MANAGE_WEBHOOKS permission - configure DISCORD_WEBHOOK_URL manually")
        except Exception as e:
            logger.error(f"Failed to setup webhook: {e}")

    def _rcon_send_packet(
        self, sock: socket.socket, packet_id: int, packet_type: int, payload: str
    ) -> None:
        """Send an RCON packet."""
        payload_bytes = payload.encode("utf-8") + b"\x00\x00"
        packet = struct.pack("<ii", packet_id, packet_type) + payload_bytes
        packet = struct.pack("<i", len(packet)) + packet
        sock.sendall(packet)

    def _rcon_recv_packet(self, sock: socket.socket) -> tuple[int, int, str]:
        """Receive an RCON packet."""
        length_data = sock.recv(4)
        if len(length_data) < 4:
            raise ConnectionError("Failed to read packet length")
        length = struct.unpack("<i", length_data)[0]

        data = b""
        while len(data) < length:
            chunk = sock.recv(length - len(data))
            if not chunk:
                raise ConnectionError("Connection closed by server")
            data += chunk

        packet_id = struct.unpack("<i", data[0:4])[0]
        packet_type = struct.unpack("<i", data[4:8])[0]
        payload = data[8:-2].decode("utf-8")

        return packet_id, packet_type, payload

    def _rcon_connect(self) -> bool:
        """Establish persistent RCON connection with authentication."""
        self._rcon_disconnect()

        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(10.0)
            sock.connect(
                (self.config.minecraft.rcon_host, self.config.minecraft.rcon_port)
            )

            self._rcon_send_packet(
                sock, 1, self.RCON_SERVERDATA_AUTH, self.config.minecraft.rcon_password
            )
            packet_id, _, _ = self._rcon_recv_packet(sock)

            if packet_id == -1:
                logger.error("RCON authentication failed - check password")
                sock.close()
                return False

            sock.settimeout(30.0)
            self._rcon_socket = sock
            self._rcon_connected = True
            logger.info("RCON connection established")
            return True

        except ConnectionRefusedError:
            logger.debug("RCON connection refused - server may be starting")
            return False
        except socket.timeout:
            logger.warning("RCON connection timed out")
            return False
        except OSError as e:
            logger.debug(f"RCON connection error: {e}")
            return False

    def _rcon_disconnect(self) -> None:
        """Close RCON connection cleanly."""
        if self._rcon_socket:
            try:
                self._rcon_socket.close()
            except OSError:
                pass
            self._rcon_socket = None
        self._rcon_connected = False

    def _rcon_sync(self, command: str) -> str:
        """Send command using persistent RCON connection with auto-reconnect."""
        if not self._rcon_connected:
            if not self._rcon_connect():
                raise ConnectionError("Not connected to RCON")

        try:
            self._rcon_send_packet(
                self._rcon_socket, 2, self.RCON_SERVERDATA_EXECCOMMAND, command
            )
            _, _, response = self._rcon_recv_packet(self._rcon_socket)
            return response

        except (socket.timeout, socket.error, ConnectionError, BrokenPipeError, OSError) as e:
            logger.warning(f"RCON command failed, connection lost: {e}")
            self._rcon_disconnect()
            raise ConnectionError(f"RCON disconnected: {e}")

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
        player_name: Optional[str] = None,
        player_uuid: Optional[str] = None,
    ) -> bool:
        """Send a message via Discord webhook."""
        # Use managed webhook if available
        if self.managed_webhook:
            try:
                avatar_url = f"https://mc-heads.net/avatar/{player_uuid}/128" if player_uuid else self.SERVER_ICON_URL
                await self.managed_webhook.send(
                    content=content,
                    username=player_name or self.config.minecraft.server_name,
                    avatar_url=avatar_url,
                )
                return True
            except discord.HTTPException as e:
                logger.error(f"Managed webhook error: {e}")
                return False

        # Fall back to manual webhook URL
        if not self.config.discord.webhook_url:
            logger.debug("No webhook available")
            return False

        if not self.http_session:
            return False

        avatar_url = f"https://mc-heads.net/avatar/{player_uuid}/128" if player_uuid else self.SERVER_ICON_URL
        payload = {
            "content": content,
            "avatar_url": avatar_url,
        }
        if player_name:
            payload["username"] = player_name

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
        icon_url: Optional[str] = None,
        author_name: Optional[str] = None,
    ) -> bool:
        """Send an embed via Discord webhook (for system messages like join/leave/status)."""
        # Build embed
        embed = discord.Embed(color=color)
        if description:
            embed.description = description
        if icon_url and author_name:
            embed.set_author(name=author_name, icon_url=icon_url)

        # Use managed webhook if available
        if self.managed_webhook:
            try:
                await self.managed_webhook.send(
                    embed=embed,
                    username=self.config.minecraft.server_name,
                    avatar_url=self.SERVER_ICON_URL,
                )
                return True
            except discord.HTTPException as e:
                logger.error(f"Managed webhook embed error: {e}")
                return False

        # Fall back to manual webhook URL
        if not self.config.discord.webhook_url:
            logger.debug("No webhook available")
            return False

        if not self.http_session:
            return False

        payload = {
            "embeds": [{"color": color, "description": description if description else None,
                       "author": {"name": author_name, "icon_url": icon_url} if icon_url and author_name else None}],
            "username": self.config.minecraft.server_name,
            "avatar_url": self.SERVER_ICON_URL,
        }

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

    async def send_bot_status(self, status: str, color: int) -> bool:
        """Send bot status notification to Discord."""
        return await self.send_webhook_embed(
            None,
            color,
            self.BOT_ICON_URL,
            status,
        )

    async def generate_player_avatars_image(self, players: list) -> Optional[io.BytesIO]:
        """Generate a combined image of player avatars (max 5 per row)."""
        if not players or not self.http_session:
            return None

        avatar_size = 32
        padding = 4
        max_per_row = 5
        avatars = []

        # Fetch all player avatars
        for player in players[:20]:  # Limit to 20 players
            if isinstance(player, dict):
                uuid = player.get("uuid", "")
            else:
                continue

            if not uuid:
                continue

            try:
                url = f"https://mc-heads.net/avatar/{uuid}/{avatar_size}"
                async with self.http_session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                    if resp.status == 200:
                        data = await resp.read()
                        img = Image.open(io.BytesIO(data))
                        avatars.append(img)
            except Exception as e:
                logger.debug(f"Failed to fetch avatar for {uuid}: {e}")
                continue

        if not avatars:
            return None

        # Calculate dimensions (max 5 per row, multiple rows if needed)
        cols = min(len(avatars), max_per_row)
        rows = (len(avatars) + max_per_row - 1) // max_per_row

        total_width = cols * avatar_size + (cols - 1) * padding
        total_height = rows * avatar_size + (rows - 1) * padding

        combined = Image.new('RGBA', (total_width, total_height), (0, 0, 0, 0))

        for i, avatar in enumerate(avatars):
            row = i // max_per_row
            col = i % max_per_row
            x = col * (avatar_size + padding)
            y = row * (avatar_size + padding)
            combined.paste(avatar, (x, y))

        # Save to buffer
        buffer = io.BytesIO()
        combined.save(buffer, format='PNG')
        buffer.seek(0)

        return buffer

    async def process_messages(self, messages: list) -> None:
        """Process messages from KubeJS (chat, join, leave)."""
        for msg in messages:
            msg_type = msg.get("type")
            player = msg.get("player", "Unknown")
            uuid = msg.get("uuid", "")

            if msg_type == "chat":
                content = msg.get("message", "")
                await self.send_webhook_message(content, player, uuid)
                logger.info(f"Relayed chat from {player}: {content[:50]}...")

            elif msg_type == "join":
                icon_url = f"https://mc-heads.net/avatar/{uuid}/32"
                await self.send_webhook_embed(
                    None,
                    self.EMBED_COLOR_GREEN,
                    icon_url,
                    f"{player} logged in",
                )
                logger.info(f"Sent join notification for {player}")

            elif msg_type == "leave":
                icon_url = f"https://mc-heads.net/avatar/{uuid}/32"
                await self.send_webhook_embed(
                    None,
                    self.EMBED_COLOR_RED,
                    icon_url,
                    f"{player} logged out",
                )
                logger.info(f"Sent leave notification for {player}")

    @tasks.loop(seconds=5)
    async def poll_server_stats(self) -> None:
        """Poll server stats via RCON and process messages."""
        stats = await self.get_stats_via_rcon()
        now = time.time()

        was_online = self.server_online

        if stats:
            self.last_stats = stats
            self.consecutive_offline_checks = 0  # Reset offline counter

            if not self.server_online:
                self.server_online = True
                # Only notify if cooldown has passed
                if now - self.last_status_notification >= self.STATUS_COOLDOWN:
                    server_name = self.config.minecraft.server_name
                    await self.send_webhook_embed(
                        None,
                        self.EMBED_COLOR_BLUE,
                        self.SERVER_ICON_URL,
                        f"{server_name} is now online!",
                    )
                    self.last_status_notification = now
                    logger.info("Server came online - sent notification")
                else:
                    logger.info("Server came online - notification skipped (cooldown)")

            messages = stats.get("messages", [])
            if messages:
                await self.process_messages(messages)
        else:
            self.consecutive_offline_checks += 1

            # Only mark offline after threshold consecutive failures
            if self.server_online and self.consecutive_offline_checks >= self.OFFLINE_THRESHOLD:
                self.server_online = False
                # Only notify if cooldown has passed
                if now - self.last_status_notification >= self.STATUS_COOLDOWN:
                    server_name = self.config.minecraft.server_name
                    await self.send_webhook_embed(
                        None,
                        self.EMBED_COLOR_ORANGE,
                        self.SERVER_ICON_URL,
                        f"{server_name} is restarting...",
                    )
                    self.last_status_notification = now
                    logger.info("Server went offline - sent notification")
                else:
                    logger.info("Server went offline - notification skipped (cooldown)")

    @poll_server_stats.before_loop
    async def before_poll_stats(self) -> None:
        self.poll_server_stats.change_interval(seconds=self.config.settings.stats_check_interval)
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

    @app_commands.command(name="players", description="Show online players on the Minecraft server")
    async def players_command(self, interaction: discord.Interaction) -> None:
        """Show online players with avatars in an embed."""
        if not self.last_stats:
            embed = discord.Embed(
                description="Unable to fetch server data. Server may be offline.",
                color=self.EMBED_COLOR_ORANGE,
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        if not self.server_online:
            embed = discord.Embed(
                description="Server is currently offline or restarting.",
                color=self.EMBED_COLOR_ORANGE,
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        players = self.last_stats.get("players", [])
        player_count = self.last_stats.get("playerCount", 0)
        server_name = self.config.minecraft.server_name
        tps = self.last_stats.get("tps", 20.0)
        uptime = self.last_stats.get("uptime", "0h 0m")

        # Build embed
        embed = discord.Embed(
            title=f"Players Online ({player_count})",
            color=self.EMBED_COLOR_GREEN if player_count > 0 else self.EMBED_COLOR_BLUE,
        )
        embed.set_author(name=server_name, icon_url=self.SERVER_ICON_URL)
        embed.set_footer(text=f"TPS: {tps:.2f} | Uptime: {uptime}")

        if player_count == 0:
            embed.description = "No players online"
            await interaction.response.send_message(embed=embed)
        else:
            # Build player list
            player_lines = []
            for player in players:
                if isinstance(player, dict):
                    name = player.get("name", "Unknown")
                else:
                    name = str(player)
                player_lines.append(f"• **{name}**")

            embed.description = "\n".join(player_lines)

            # Generate combined avatar image
            avatar_buffer = await self.generate_player_avatars_image(players)

            if avatar_buffer:
                file = discord.File(avatar_buffer, filename="players.png")
                embed.set_image(url="attachment://players.png")
                await interaction.response.send_message(embed=embed, file=file)
            else:
                await interaction.response.send_message(embed=embed)


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
        self._shutdown_notification_sent = False

    async def setup_hook(self) -> None:
        """Called when bot is starting up."""
        await self.add_cog(MinecraftBridge(self, self.config))

        # Sync slash commands
        try:
            if self.config.discord.guild_id:
                # Sync to specific guild for instant updates during development
                guild = discord.Object(id=self.config.discord.guild_id)
                self.tree.copy_global_to(guild=guild)
                await self.tree.sync(guild=guild)
                logger.info(f"Synced commands to guild {self.config.discord.guild_id}")
            else:
                # Global sync (can take up to an hour to propagate)
                await self.tree.sync()
                logger.info("Synced commands globally")
        except discord.Forbidden as e:
            logger.warning(f"Missing access to sync commands: {e.status} {e.code} - {e.text}")
        except Exception as e:
            logger.error(f"Failed to sync commands: {e}")

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

        # Setup webhook (must be done after bot is ready to access channels)
        bridge = self.get_cog("MinecraftBridge")
        if bridge:
            await bridge.setup_webhook()
            # Send bot startup notification
            await bridge.send_bot_status(
                "Discord bot started",
                MinecraftBridge.EMBED_COLOR_PURPLE,
            )
            logger.info("Sent bot startup notification")

    async def close(self) -> None:
        """Called when bot is shutting down."""
        if not self._shutdown_notification_sent:
            self._shutdown_notification_sent = True
            bridge = self.get_cog("MinecraftBridge")
            if bridge:
                await bridge.send_bot_status(
                    "Discord bot stopped",
                    MinecraftBridge.EMBED_COLOR_RED,
                )
                logger.info("Sent bot shutdown notification")
        await super().close()


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

    # Set up signal handlers for graceful shutdown
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    async def shutdown() -> None:
        """Graceful shutdown coroutine."""
        logger.info("Shutting down bot...")
        await bot.close()
        logger.info("Bot shutdown complete")

    def handle_signal(sig: signal.Signals) -> None:
        logger.info(f"Received signal {sig.name}, initiating shutdown...")
        # Stop the bot by cancelling the main task
        for task in asyncio.all_tasks(loop):
            task.cancel()

    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, handle_signal, sig)

    try:
        loop.run_until_complete(bot.start(config.discord.token))
    except asyncio.CancelledError:
        logger.info("Main task cancelled, running shutdown...")
        loop.run_until_complete(shutdown())
    except discord.LoginFailure:
        logger.error("Invalid Discord token")
    except Exception as e:
        logger.error(f"Bot crashed: {e}")
    finally:
        loop.run_until_complete(loop.shutdown_asyncgens())
        loop.close()


if __name__ == "__main__":
    main()
