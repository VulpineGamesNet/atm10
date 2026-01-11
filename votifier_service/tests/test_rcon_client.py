"""Tests for RCON client."""

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from config import RconConfig
from rcon_client import RconClient


class TestRconClientInit:
    """Tests for RconClient initialization."""

    def test_init_with_config(self, rcon_config):
        client = RconClient(rcon_config)

        assert client.config == rcon_config
        assert client.config.host == "localhost"
        assert client.config.port == 25575
        assert client.config.password == "test_password"


class TestRconClientExecute:
    """Tests for RconClient.execute method."""

    def test_execute_command_success(self, rcon_config, mock_mcrcon):
        mock_class, mock_instance = mock_mcrcon
        mock_instance.command.return_value = "There are 5 players online"

        client = RconClient(rcon_config)
        result = client.execute("list")

        assert result == "There are 5 players online"
        mock_class.assert_called_once_with(
            host=rcon_config.host,
            password=rcon_config.password,
            port=rcon_config.port,
        )
        mock_instance.command.assert_called_once_with("list")

    def test_execute_command_with_arguments(self, rcon_config, mock_mcrcon):
        mock_class, mock_instance = mock_mcrcon
        mock_instance.command.return_value = "Set TestPlayer balance to 1000"

        client = RconClient(rcon_config)
        result = client.execute("wallet admin setbalance TestPlayer 1000")

        assert result == "Set TestPlayer balance to 1000"
        mock_instance.command.assert_called_once_with("wallet admin setbalance TestPlayer 1000")

    def test_execute_command_connection_error(self, rcon_config, mocker):
        mock_class = mocker.patch("rcon_client.MCRcon")
        mock_class.side_effect = ConnectionRefusedError("Connection refused")

        client = RconClient(rcon_config)

        with pytest.raises(ConnectionRefusedError):
            client.execute("list")

    def test_execute_command_timeout(self, rcon_config, mocker):
        mock_class = mocker.patch("rcon_client.MCRcon")
        mock_class.side_effect = TimeoutError("Connection timed out")

        client = RconClient(rcon_config)

        with pytest.raises(TimeoutError):
            client.execute("list")


class TestRconClientProcessVote:
    """Tests for RconClient.process_vote method."""

    def test_process_vote_success(self, rcon_config, mock_mcrcon):
        mock_class, mock_instance = mock_mcrcon
        mock_instance.command.return_value = "Vote processed successfully"

        client = RconClient(rcon_config)
        result = client.process_vote("TestPlayer", "PlanetMinecraft")

        assert result == "Vote processed successfully"
        mock_instance.command.assert_called_once_with("kubevote process TestPlayer PlanetMinecraft")

    def test_process_vote_with_special_service_name(self, rcon_config, mock_mcrcon):
        mock_class, mock_instance = mock_mcrcon
        mock_instance.command.return_value = "Vote processed"

        client = RconClient(rcon_config)
        client.process_vote("Player123", "minecraft-server-list")

        mock_instance.command.assert_called_once_with("kubevote process Player123 minecraft-server-list")

    def test_process_vote_failure(self, rcon_config, mocker):
        mock_class = mocker.patch("rcon_client.MCRcon")
        mock_class.side_effect = Exception("RCON error")

        client = RconClient(rcon_config)

        with pytest.raises(Exception, match="RCON error"):
            client.process_vote("Player", "Service")


class TestRconClientTestConnection:
    """Tests for RconClient.test_connection method."""

    def test_connection_success(self, rcon_config, mock_mcrcon):
        mock_class, mock_instance = mock_mcrcon
        mock_instance.command.return_value = "There are 0 of a max of 20 players online"

        client = RconClient(rcon_config)
        result = client.test_connection()

        assert result is True
        mock_instance.command.assert_called_once_with("list")

    def test_connection_failure(self, rcon_config, mocker):
        mock_class = mocker.patch("rcon_client.MCRcon")
        mock_class.side_effect = ConnectionRefusedError("Connection refused")

        client = RconClient(rcon_config)
        result = client.test_connection()

        assert result is False

    def test_connection_timeout(self, rcon_config, mocker):
        mock_class = mocker.patch("rcon_client.MCRcon")
        mock_class.side_effect = TimeoutError("Timed out")

        client = RconClient(rcon_config)
        result = client.test_connection()

        assert result is False


class TestRconClientIntegration:
    """Integration tests for RconClient."""

    def test_multiple_commands(self, rcon_config, mock_mcrcon):
        mock_class, mock_instance = mock_mcrcon
        mock_instance.command.side_effect = [
            "Player list",
            "Balance: 1000",
            "Vote processed",
        ]

        client = RconClient(rcon_config)

        assert client.execute("list") == "Player list"
        assert client.execute("wallet balance Player") == "Balance: 1000"
        assert client.process_vote("Player", "Site") == "Vote processed"

        assert mock_instance.command.call_count == 3
