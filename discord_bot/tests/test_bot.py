"""Tests for the Discord bot functionality."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest

from bot import DiscordMCBot, MinecraftBridge
from config import Config, DiscordConfig, MinecraftConfig, Settings


@pytest.fixture
def config():
    """Create a test configuration."""
    return Config(
        discord=DiscordConfig(
            token="test_token",
            channel_id=123456789,
            webhook_url="https://discord.com/api/webhooks/test",
            guild_id=987654321,
        ),
        minecraft=MinecraftConfig(
            rcon_host="localhost",
            rcon_port=25575,
            rcon_password="test_password",
            server_name="Test Server",
        ),
        settings=Settings(
            topic_update_interval=60,
            stats_check_interval=5,
            max_message_length=256,
        ),
    )


@pytest.fixture
def mock_bot(config):
    """Create a mock bot instance."""
    bot = MagicMock(spec=DiscordMCBot)
    bot.config = config
    bot.wait_until_ready = AsyncMock()
    bot.get_channel = MagicMock(return_value=None)
    return bot


@pytest.fixture
def bridge(mock_bot, config):
    """Create a MinecraftBridge instance for testing."""
    return MinecraftBridge(mock_bot, config)


class TestMessageSanitization:
    """Tests for Discord message sanitization."""

    def test_sanitize_removes_user_mentions(self, bridge):
        """Test that user mentions are replaced."""
        result = bridge.sanitize_discord_message("Hello <@123456789>!")
        assert result == "Hello [mention]!"

    def test_sanitize_removes_user_mentions_with_exclamation(self, bridge):
        """Test that user mentions with ! are replaced."""
        result = bridge.sanitize_discord_message("Hello <@!123456789>!")
        assert result == "Hello [mention]!"

    def test_sanitize_removes_channel_mentions(self, bridge):
        """Test that channel mentions are replaced."""
        result = bridge.sanitize_discord_message("Check out <#123456789>")
        assert result == "Check out [channel]"

    def test_sanitize_removes_role_mentions(self, bridge):
        """Test that role mentions are replaced."""
        result = bridge.sanitize_discord_message("Hey <@&123456789>!")
        assert result == "Hey [role]!"

    def test_sanitize_converts_custom_emojis(self, bridge):
        """Test that custom emojis are converted to text."""
        result = bridge.sanitize_discord_message("Nice <:thumbsup:123456>")
        assert result == "Nice :thumbsup:"

    def test_sanitize_converts_animated_emojis(self, bridge):
        """Test that animated emojis are converted to text."""
        result = bridge.sanitize_discord_message("Cool <a:dance:123456>")
        assert result == "Cool :dance:"

    def test_sanitize_replaces_quotes(self, bridge):
        """Test that double quotes are replaced with single quotes."""
        result = bridge.sanitize_discord_message('He said "hello"')
        assert result == "He said 'hello'"

    def test_sanitize_removes_backslashes(self, bridge):
        """Test that backslashes are removed."""
        result = bridge.sanitize_discord_message("Path\\to\\file")
        assert result == "Pathtofile"

    def test_sanitize_replaces_newlines(self, bridge):
        """Test that newlines are replaced with spaces."""
        result = bridge.sanitize_discord_message("Line1\nLine2\rLine3")
        assert result == "Line1 Line2 Line3"

    def test_sanitize_collapses_multiple_spaces(self, bridge):
        """Test that multiple spaces are collapsed."""
        result = bridge.sanitize_discord_message("Too    many   spaces")
        assert result == "Too many spaces"

    def test_sanitize_truncates_long_messages(self, bridge):
        """Test that long messages are truncated."""
        long_message = "x" * 300
        result = bridge.sanitize_discord_message(long_message)
        assert len(result) == 256
        assert result.endswith("...")

    def test_sanitize_preserves_normal_text(self, bridge):
        """Test that normal text is preserved."""
        result = bridge.sanitize_discord_message("Hello, world!")
        assert result == "Hello, world!"

    def test_sanitize_strips_whitespace(self, bridge):
        """Test that leading/trailing whitespace is stripped."""
        result = bridge.sanitize_discord_message("  Hello  ")
        assert result == "Hello"

    def test_sanitize_complex_message(self, bridge):
        """Test sanitization of a complex message."""
        message = 'Hey <@123> check <#456>! <:emoji:789> said "test"\nNew line'
        result = bridge.sanitize_discord_message(message)
        assert result == "Hey [mention] check [channel]! :emoji: said 'test' New line"


class TestUsernameSanitization:
    """Tests for Discord username sanitization."""

    def test_sanitize_username_normal(self, bridge):
        """Test that normal usernames are preserved."""
        result = bridge.sanitize_username("TestUser")
        assert result == "TestUser"

    def test_sanitize_username_with_spaces(self, bridge):
        """Test that spaces are preserved."""
        result = bridge.sanitize_username("Test User")
        assert result == "Test User"

    def test_sanitize_username_with_special_chars(self, bridge):
        """Test that special characters are removed."""
        result = bridge.sanitize_username("Test@User#123!")
        assert result == "TestUser123"

    def test_sanitize_username_truncates(self, bridge):
        """Test that long usernames are truncated to 16 characters."""
        result = bridge.sanitize_username("VeryLongUsernameHere")
        assert result == "VeryLongUsername"
        assert len(result) == 16

    def test_sanitize_username_empty_returns_default(self, bridge):
        """Test that empty username returns 'Discord'."""
        result = bridge.sanitize_username("")
        assert result == "Discord"

    def test_sanitize_username_only_special_chars(self, bridge):
        """Test that username with only special chars returns default."""
        result = bridge.sanitize_username("@#$%^&*()")
        assert result == "Discord"

    def test_sanitize_username_with_dashes_underscores(self, bridge):
        """Test that dashes and underscores are preserved."""
        result = bridge.sanitize_username("Test-User_123")
        assert result == "Test-User_123"


class TestRCONStats:
    """Tests for RCON-based stats retrieval."""

    @pytest.mark.asyncio
    async def test_get_stats_via_rcon_success(self, bridge):
        """Test successful stats retrieval via RCON."""
        stats_json = json.dumps({
            "tps": 19.5,
            "playerCount": 5,
            "players": ["Player1", "Player2"],
            "uptime": "2h 30m",
            "messages": [],
        })
        with patch.object(bridge, "send_rcon_command", new_callable=AsyncMock, return_value=stats_json):
            result = await bridge.get_stats_via_rcon()

        assert result is not None
        assert result["tps"] == 19.5
        assert result["playerCount"] == 5

    @pytest.mark.asyncio
    async def test_get_stats_via_rcon_failure(self, bridge):
        """Test stats retrieval when RCON fails."""
        with patch.object(bridge, "send_rcon_command", new_callable=AsyncMock, return_value=None):
            result = await bridge.get_stats_via_rcon()

        assert result is None

    @pytest.mark.asyncio
    async def test_get_stats_via_rcon_invalid_json(self, bridge):
        """Test stats retrieval with invalid JSON response."""
        with patch.object(bridge, "send_rcon_command", new_callable=AsyncMock, return_value="not valid json"):
            result = await bridge.get_stats_via_rcon()

        assert result is None


class TestRCON:
    """Tests for RCON functionality."""

    @pytest.mark.asyncio
    async def test_send_rcon_command_success(self, bridge):
        """Test successful RCON command."""
        with patch.object(bridge, "_rcon_sync", return_value="Command executed"):
            result = await bridge.send_rcon_command("test command")

        assert result == "Command executed"

    @pytest.mark.asyncio
    async def test_send_rcon_command_failure(self, bridge):
        """Test RCON command failure."""
        with patch.object(bridge, "_rcon_sync", side_effect=Exception("Connection failed")):
            result = await bridge.send_rcon_command("test command")

        assert result is None


class TestMessageHandler:
    """Tests for Discord message handling."""

    @pytest.fixture
    def mock_message(self, config):
        """Create a mock Discord message."""
        message = MagicMock(spec=discord.Message)
        message.author = MagicMock()
        message.author.bot = False
        message.author.display_name = "TestUser"
        message.channel = MagicMock()
        message.channel.id = config.discord.channel_id
        message.content = "Hello from Discord!"
        message.attachments = []
        message.stickers = []
        message.add_reaction = AsyncMock()
        return message

    @pytest.mark.asyncio
    async def test_on_message_ignores_bots(self, bridge, mock_message):
        """Test that bot messages are ignored."""
        mock_message.author.bot = True

        with patch.object(bridge, "send_rcon_command", new_callable=AsyncMock) as mock_rcon:
            await bridge.on_message(mock_message)

        mock_rcon.assert_not_called()

    @pytest.mark.asyncio
    async def test_on_message_ignores_wrong_channel(self, bridge, mock_message):
        """Test that messages from wrong channel are ignored."""
        mock_message.channel.id = 999999999  # Different channel

        with patch.object(bridge, "send_rcon_command", new_callable=AsyncMock) as mock_rcon:
            await bridge.on_message(mock_message)

        mock_rcon.assert_not_called()

    @pytest.mark.asyncio
    async def test_on_message_relays_to_minecraft(self, bridge, mock_message):
        """Test that valid messages are relayed to Minecraft."""
        with patch.object(
            bridge, "send_rcon_command", new_callable=AsyncMock, return_value="OK"
        ) as mock_rcon:
            await bridge.on_message(mock_message)

        mock_rcon.assert_called_once()
        call_args = mock_rcon.call_args[0][0]
        assert "discordmsg" in call_args
        assert "TestUser" in call_args
        assert "Hello from Discord!" in call_args

    @pytest.mark.asyncio
    async def test_on_message_handles_attachments(self, bridge, mock_message):
        """Test that attachment-only messages are handled."""
        mock_message.content = ""
        mock_message.attachments = [MagicMock()]

        with patch.object(
            bridge, "send_rcon_command", new_callable=AsyncMock, return_value="OK"
        ) as mock_rcon:
            await bridge.on_message(mock_message)

        mock_rcon.assert_called_once()
        call_args = mock_rcon.call_args[0][0]
        assert "[attachment]" in call_args

    @pytest.mark.asyncio
    async def test_on_message_handles_stickers(self, bridge, mock_message):
        """Test that sticker-only messages are handled."""
        mock_message.content = ""
        mock_message.stickers = [MagicMock()]

        with patch.object(
            bridge, "send_rcon_command", new_callable=AsyncMock, return_value="OK"
        ) as mock_rcon:
            await bridge.on_message(mock_message)

        mock_rcon.assert_called_once()
        call_args = mock_rcon.call_args[0][0]
        assert "[sticker]" in call_args

    @pytest.mark.asyncio
    async def test_on_message_ignores_empty(self, bridge, mock_message):
        """Test that empty messages without attachments are ignored."""
        mock_message.content = ""
        mock_message.attachments = []
        mock_message.stickers = []

        with patch.object(bridge, "send_rcon_command", new_callable=AsyncMock) as mock_rcon:
            await bridge.on_message(mock_message)

        mock_rcon.assert_not_called()

    @pytest.mark.asyncio
    async def test_on_message_no_reaction_on_success(self, bridge, mock_message):
        """Test that no reaction is added on successful relay."""
        with patch.object(
            bridge, "send_rcon_command", new_callable=AsyncMock, return_value="OK"
        ):
            await bridge.on_message(mock_message)

        mock_message.add_reaction.assert_not_called()

    @pytest.mark.asyncio
    async def test_on_message_replies_on_failure(self, bridge, mock_message):
        """Test that failure reply is sent when relay fails."""
        mock_message.reply = AsyncMock()
        with patch.object(
            bridge, "send_rcon_command", new_callable=AsyncMock, return_value=None
        ):
            await bridge.on_message(mock_message)

        mock_message.reply.assert_called_once()
        call_kwargs = mock_message.reply.call_args.kwargs
        assert call_kwargs["mention_author"] is False
        embed = call_kwargs["embed"]
        assert "not delivered" in embed.description.lower()


class TestChannelTopicUpdate:
    """Tests for channel topic update functionality."""

    @pytest.mark.asyncio
    async def test_update_topic_no_stats(self, bridge):
        """Test that topic update is skipped when no stats available."""
        bridge.last_stats = None

        await bridge.update_channel_topic()

        bridge.bot.get_channel.assert_not_called()

    @pytest.mark.asyncio
    async def test_update_topic_channel_not_found(self, bridge):
        """Test handling when channel is not found."""
        bridge.last_stats = {"tps": 20.0, "playerCount": 5, "uptime": "1h 0m"}
        bridge.bot.get_channel.return_value = None

        # Should not raise
        await bridge.update_channel_topic()

    @pytest.mark.asyncio
    async def test_update_topic_formats_correctly(self, bridge):
        """Test that topic is formatted correctly."""
        bridge.last_stats = {
            "tps": 19.85,
            "playerCount": 42,
            "uptime": "21h 1m",
        }
        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_channel.topic = None
        mock_channel.edit = AsyncMock()
        bridge.bot.get_channel.return_value = mock_channel

        await bridge.update_channel_topic()

        mock_channel.edit.assert_called_once()
        topic = mock_channel.edit.call_args.kwargs["topic"]
        assert topic == "TPS: 19.85 | Players: 42 | Uptime: 21h 1m"

    @pytest.mark.asyncio
    async def test_update_topic_skips_if_unchanged(self, bridge):
        """Test that topic update is skipped if topic hasn't changed."""
        bridge.last_stats = {"tps": 20.0, "playerCount": 5, "uptime": "1h 0m"}
        bridge.last_topic = "TPS: 20.00 | Players: 5 | Uptime: 1h 0m"
        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_channel.edit = AsyncMock()
        bridge.bot.get_channel.return_value = mock_channel

        await bridge.update_channel_topic()

        mock_channel.edit.assert_not_called()


class TestServerStatusDetection:
    """Tests for server start/stop detection."""

    @pytest.mark.asyncio
    async def test_server_comes_online(self, bridge):
        """Test detection when server comes online."""
        bridge.server_online = False
        stats = {"tps": 20.0, "playerCount": 0, "messages": []}

        with patch.object(bridge, "get_stats_via_rcon", new_callable=AsyncMock, return_value=stats):
            with patch.object(bridge, "send_webhook_embed", new_callable=AsyncMock) as mock_embed:
                await bridge.poll_server_stats()

        assert bridge.server_online is True
        mock_embed.assert_called_once()
        assert "online" in mock_embed.call_args[0][0].lower()

    @pytest.mark.asyncio
    async def test_server_goes_offline(self, bridge):
        """Test detection when server goes offline."""
        bridge.server_online = True

        with patch.object(bridge, "get_stats_via_rcon", new_callable=AsyncMock, return_value=None):
            with patch.object(bridge, "send_webhook_embed", new_callable=AsyncMock) as mock_embed:
                await bridge.poll_server_stats()

        assert bridge.server_online is False
        mock_embed.assert_called_once()
        assert "restarting" in mock_embed.call_args[0][0].lower()

    @pytest.mark.asyncio
    async def test_server_stays_online(self, bridge):
        """Test no notification when server stays online."""
        bridge.server_online = True
        stats = {"tps": 20.0, "playerCount": 0, "messages": []}

        with patch.object(bridge, "get_stats_via_rcon", new_callable=AsyncMock, return_value=stats):
            with patch.object(bridge, "send_webhook_embed", new_callable=AsyncMock) as mock_embed:
                await bridge.poll_server_stats()

        assert bridge.server_online is True
        mock_embed.assert_not_called()


class TestMessageProcessing:
    """Tests for processing messages from KubeJS."""

    @pytest.mark.asyncio
    async def test_process_chat_message(self, bridge):
        """Test processing a chat message."""
        messages = [{"type": "chat", "player": "Steve", "uuid": "abc-123", "message": "Hello!"}]

        with patch.object(bridge, "send_webhook_message", new_callable=AsyncMock) as mock_webhook:
            await bridge.process_messages(messages)

        mock_webhook.assert_called_once()
        assert mock_webhook.call_args[0][0] == "Hello!"
        assert mock_webhook.call_args[0][1] == "Steve"

    @pytest.mark.asyncio
    async def test_process_join_message(self, bridge):
        """Test processing a join message."""
        messages = [{"type": "join", "player": "Steve", "uuid": "abc-123"}]

        with patch.object(bridge, "send_webhook_embed", new_callable=AsyncMock) as mock_embed:
            await bridge.process_messages(messages)

        mock_embed.assert_called_once()
        args = mock_embed.call_args[0]
        assert args[0] is None  # no description
        assert "Steve logged in" in args[3]  # author_name

    @pytest.mark.asyncio
    async def test_process_leave_message(self, bridge):
        """Test processing a leave message."""
        messages = [{"type": "leave", "player": "Steve", "uuid": "abc-123"}]

        with patch.object(bridge, "send_webhook_embed", new_callable=AsyncMock) as mock_embed:
            await bridge.process_messages(messages)

        mock_embed.assert_called_once()
        args = mock_embed.call_args[0]
        assert args[0] is None  # no description
        assert "Steve logged out" in args[3]  # author_name


class TestDiscordMCBot:
    """Tests for the main bot class."""

    def test_bot_initialization(self, config):
        """Test bot initialization with config."""
        bot = DiscordMCBot(config)

        assert bot.config == config
        assert bot.command_prefix == "!mc"

    def test_bot_intents(self, config):
        """Test that bot has correct intents."""
        bot = DiscordMCBot(config)

        assert bot.intents.message_content is True
        assert bot.intents.guilds is True
