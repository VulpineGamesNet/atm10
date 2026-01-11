"""Tests for RCON client."""

import socket
import struct
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
        assert client._socket is None
        assert client._connected is False


class TestRconClientConnect:
    """Tests for RconClient connection methods."""

    def test_connect_success(self, rcon_config, mock_rcon_socket):
        mock_socket_class, mock_sock, create_response = mock_rcon_socket

        client = RconClient(rcon_config)
        result = client._connect()

        assert result is True
        assert client._connected is True
        assert client._socket is mock_sock
        mock_sock.connect.assert_called_once_with(("localhost", 25575))

    def test_connect_auth_failure(self, rcon_config, mocker):
        mock_sock = MagicMock()

        # Auth failure returns packet_id -1
        def create_response(packet_id: int, response: str) -> bytes:
            payload = response.encode("utf-8") + b"\x00\x00"
            packet = struct.pack("<ii", packet_id, 0) + payload
            return struct.pack("<i", len(packet)) + packet

        auth_response = create_response(-1, "")
        mock_sock.recv.side_effect = [
            auth_response[:4],
            auth_response[4:],
        ]

        mocker.patch("rcon_client.socket.socket", return_value=mock_sock)

        client = RconClient(rcon_config)
        result = client._connect()

        assert result is False
        assert client._connected is False
        mock_sock.close.assert_called_once()

    def test_connect_refused(self, rcon_config, mocker):
        mock_sock = MagicMock()
        mock_sock.connect.side_effect = ConnectionRefusedError("Connection refused")
        mocker.patch("rcon_client.socket.socket", return_value=mock_sock)

        client = RconClient(rcon_config)
        result = client._connect()

        assert result is False
        assert client._connected is False

    def test_connect_timeout(self, rcon_config, mocker):
        mock_sock = MagicMock()
        mock_sock.connect.side_effect = socket.timeout("Timed out")
        mocker.patch("rcon_client.socket.socket", return_value=mock_sock)

        client = RconClient(rcon_config)
        result = client._connect()

        assert result is False
        assert client._connected is False

    def test_disconnect(self, rcon_config, mock_rcon_socket):
        mock_socket_class, mock_sock, create_response = mock_rcon_socket

        client = RconClient(rcon_config)
        client._connect()

        client._disconnect()

        assert client._connected is False
        assert client._socket is None
        mock_sock.close.assert_called()

    def test_close(self, rcon_config, mock_rcon_socket):
        mock_socket_class, mock_sock, create_response = mock_rcon_socket

        client = RconClient(rcon_config)
        client._connect()

        client.close()

        assert client._connected is False
        assert client._socket is None


class TestRconClientExecute:
    """Tests for RconClient.execute method."""

    def test_execute_command_success(self, rcon_config, mocker):
        mock_sock = MagicMock()

        def create_response(packet_id: int, response: str) -> bytes:
            payload = response.encode("utf-8") + b"\x00\x00"
            packet = struct.pack("<ii", packet_id, 0) + payload
            return struct.pack("<i", len(packet)) + packet

        auth_response = create_response(1, "")
        command_response = create_response(2, "There are 5 players online")

        mock_sock.recv.side_effect = [
            auth_response[:4],
            auth_response[4:],
            command_response[:4],
            command_response[4:],
        ]

        mocker.patch("rcon_client.socket.socket", return_value=mock_sock)

        client = RconClient(rcon_config)
        result = client.execute("list")

        assert result == "There are 5 players online"

    def test_execute_command_with_arguments(self, rcon_config, mocker):
        mock_sock = MagicMock()

        def create_response(packet_id: int, response: str) -> bytes:
            payload = response.encode("utf-8") + b"\x00\x00"
            packet = struct.pack("<ii", packet_id, 0) + payload
            return struct.pack("<i", len(packet)) + packet

        auth_response = create_response(1, "")
        command_response = create_response(2, "Set TestPlayer balance to 1000")

        mock_sock.recv.side_effect = [
            auth_response[:4],
            auth_response[4:],
            command_response[:4],
            command_response[4:],
        ]

        mocker.patch("rcon_client.socket.socket", return_value=mock_sock)

        client = RconClient(rcon_config)
        result = client.execute("wallet admin setbalance TestPlayer 1000")

        assert result == "Set TestPlayer balance to 1000"

    def test_execute_command_connection_error(self, rcon_config, mocker):
        mock_sock = MagicMock()
        mock_sock.connect.side_effect = ConnectionRefusedError("Connection refused")
        mocker.patch("rcon_client.socket.socket", return_value=mock_sock)

        client = RconClient(rcon_config)

        with pytest.raises(ConnectionError):
            client.execute("list")

    def test_execute_command_timeout(self, rcon_config, mocker):
        mock_sock = MagicMock()
        mock_sock.connect.side_effect = socket.timeout("Connection timed out")
        mocker.patch("rcon_client.socket.socket", return_value=mock_sock)

        client = RconClient(rcon_config)

        with pytest.raises(ConnectionError):
            client.execute("list")

    def test_execute_reconnects_on_failure(self, rcon_config, mocker):
        """Test that execute reconnects if connection is lost during command."""
        mock_sock = MagicMock()

        def create_response(packet_id: int, response: str) -> bytes:
            payload = response.encode("utf-8") + b"\x00\x00"
            packet = struct.pack("<ii", packet_id, 0) + payload
            return struct.pack("<i", len(packet)) + packet

        auth_response = create_response(1, "")

        # First call succeeds auth, then command fails with broken pipe
        mock_sock.recv.side_effect = [
            auth_response[:4],
            auth_response[4:],
        ]
        mock_sock.sendall.side_effect = [
            None,  # Auth packet
            BrokenPipeError("Broken pipe"),  # Command fails
        ]

        mocker.patch("rcon_client.socket.socket", return_value=mock_sock)

        client = RconClient(rcon_config)

        with pytest.raises(ConnectionError, match="RCON disconnected"):
            client.execute("list")

        # Connection should be marked as disconnected
        assert client._connected is False


class TestRconClientProcessVote:
    """Tests for RconClient.process_vote method."""

    def test_process_vote_success(self, rcon_config, mocker):
        mock_sock = MagicMock()

        def create_response(packet_id: int, response: str) -> bytes:
            payload = response.encode("utf-8") + b"\x00\x00"
            packet = struct.pack("<ii", packet_id, 0) + payload
            return struct.pack("<i", len(packet)) + packet

        auth_response = create_response(1, "")
        command_response = create_response(2, "Vote processed successfully")

        mock_sock.recv.side_effect = [
            auth_response[:4],
            auth_response[4:],
            command_response[:4],
            command_response[4:],
        ]

        mocker.patch("rcon_client.socket.socket", return_value=mock_sock)

        client = RconClient(rcon_config)
        result = client.process_vote("TestPlayer", "PlanetMinecraft")

        assert result == "Vote processed successfully"

    def test_process_vote_with_space_in_service_name(self, rcon_config, mocker):
        mock_sock = MagicMock()

        def create_response(packet_id: int, response: str) -> bytes:
            payload = response.encode("utf-8") + b"\x00\x00"
            packet = struct.pack("<ii", packet_id, 0) + payload
            return struct.pack("<i", len(packet)) + packet

        auth_response = create_response(1, "")
        command_response = create_response(2, "Vote processed")

        mock_sock.recv.side_effect = [
            auth_response[:4],
            auth_response[4:],
            command_response[:4],
            command_response[4:],
        ]

        sent_packets = []
        def capture_sendall(data):
            sent_packets.append(data)

        mock_sock.sendall.side_effect = capture_sendall

        mocker.patch("rcon_client.socket.socket", return_value=mock_sock)

        client = RconClient(rcon_config)
        client.process_vote("Player123", "minecraft server list")

        # Verify spaces are replaced with underscores
        assert b"minecraft_server_list" in sent_packets[-1]

    def test_process_vote_failure(self, rcon_config, mocker):
        mock_sock = MagicMock()
        mock_sock.connect.side_effect = ConnectionRefusedError("RCON error")
        mocker.patch("rcon_client.socket.socket", return_value=mock_sock)

        client = RconClient(rcon_config)

        with pytest.raises(ConnectionError):
            client.process_vote("Player", "Service")


class TestRconClientTestConnection:
    """Tests for RconClient.test_connection method."""

    def test_connection_success(self, rcon_config, mocker):
        mock_sock = MagicMock()

        def create_response(packet_id: int, response: str) -> bytes:
            payload = response.encode("utf-8") + b"\x00\x00"
            packet = struct.pack("<ii", packet_id, 0) + payload
            return struct.pack("<i", len(packet)) + packet

        auth_response = create_response(1, "")
        command_response = create_response(2, "There are 0 of a max of 20 players online")

        mock_sock.recv.side_effect = [
            auth_response[:4],
            auth_response[4:],
            command_response[:4],
            command_response[4:],
        ]

        mocker.patch("rcon_client.socket.socket", return_value=mock_sock)

        client = RconClient(rcon_config)
        result = client.test_connection()

        assert result is True

    def test_connection_failure(self, rcon_config, mocker):
        mock_sock = MagicMock()
        mock_sock.connect.side_effect = ConnectionRefusedError("Connection refused")
        mocker.patch("rcon_client.socket.socket", return_value=mock_sock)

        client = RconClient(rcon_config)
        result = client.test_connection()

        assert result is False

    def test_connection_timeout(self, rcon_config, mocker):
        mock_sock = MagicMock()
        mock_sock.connect.side_effect = socket.timeout("Timed out")
        mocker.patch("rcon_client.socket.socket", return_value=mock_sock)

        client = RconClient(rcon_config)
        result = client.test_connection()

        assert result is False


class TestRconClientIntegration:
    """Integration tests for RconClient."""

    def test_multiple_commands_reuse_connection(self, rcon_config, mocker):
        """Test that multiple commands reuse the same connection."""
        mock_sock = MagicMock()

        def create_response(packet_id: int, response: str) -> bytes:
            payload = response.encode("utf-8") + b"\x00\x00"
            packet = struct.pack("<ii", packet_id, 0) + payload
            return struct.pack("<i", len(packet)) + packet

        auth_response = create_response(1, "")

        # Auth once, then 3 commands
        mock_sock.recv.side_effect = [
            auth_response[:4],
            auth_response[4:],
            create_response(2, "Player list")[:4],
            create_response(2, "Player list")[4:],
            create_response(2, "Balance: 1000")[:4],
            create_response(2, "Balance: 1000")[4:],
            create_response(2, "Vote processed")[:4],
            create_response(2, "Vote processed")[4:],
        ]

        mock_socket_class = mocker.patch("rcon_client.socket.socket", return_value=mock_sock)

        client = RconClient(rcon_config)

        assert client.execute("list") == "Player list"
        assert client.execute("wallet balance Player") == "Balance: 1000"
        assert client.process_vote("Player", "Site") == "Vote processed"

        # Socket should only be created once (persistent connection)
        assert mock_socket_class.call_count == 1
        # Connect should only be called once
        assert mock_sock.connect.call_count == 1
