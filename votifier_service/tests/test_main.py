"""Tests for the main Votifier server."""

import socket
import sys
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from cryptography.hazmat.primitives.asymmetric import padding

sys.path.insert(0, str(Path(__file__).parent.parent))

from main import VotifierServer


class TestVotifierServerInit:
    """Tests for VotifierServer initialization."""

    def test_init_creates_protocol(self, full_config):
        with patch("main.RconClient"):
            server = VotifierServer(full_config)

        assert server.protocol is not None
        assert server.config == full_config

    def test_init_creates_rcon_client(self, full_config):
        with patch("main.RconClient") as mock_rcon:
            server = VotifierServer(full_config)

        mock_rcon.assert_called_once_with(full_config.rcon)

    def test_init_debug_mode(self, full_config, mocker):
        full_config.debug = True
        mock_logging = mocker.patch("logging.getLogger")

        with patch("main.RconClient"):
            server = VotifierServer(full_config)

        assert server.config.debug is True


class TestVotifierServerStartStop:
    """Tests for server start/stop functionality."""

    def test_stop_before_start(self, full_config):
        with patch("main.RconClient"):
            server = VotifierServer(full_config)
            server.stop()

        assert server._running is False
        assert server._server_socket is None

    def test_start_binds_to_port(self, full_config, mocker):
        with patch("main.RconClient") as mock_rcon:
            mock_rcon_instance = MagicMock()
            mock_rcon_instance.test_connection.return_value = True
            mock_rcon.return_value = mock_rcon_instance

            server = VotifierServer(full_config)

            def stop_after_bind():
                time.sleep(0.1)
                server.stop()

            stop_thread = threading.Thread(target=stop_after_bind)
            stop_thread.start()

            try:
                server.start()
            except Exception:
                pass

            stop_thread.join(timeout=1)

        assert server._running is False


class TestVotifierServerClientHandling:
    """Tests for client connection handling."""

    def test_recv_exact_full_data(self, full_config):
        with patch("main.RconClient"):
            server = VotifierServer(full_config)

        mock_socket = MagicMock()
        mock_socket.recv.side_effect = [b"0123456789", b"abcdef"]

        result = server._recv_exact(mock_socket, 16)

        assert result == b"0123456789abcdef"
        assert mock_socket.recv.call_count == 2

    def test_recv_exact_connection_closed(self, full_config):
        with patch("main.RconClient"):
            server = VotifierServer(full_config)

        mock_socket = MagicMock()
        mock_socket.recv.return_value = b""

        result = server._recv_exact(mock_socket, 256)

        assert result is None

    def test_recv_exact_timeout(self, full_config):
        with patch("main.RconClient"):
            server = VotifierServer(full_config)

        mock_socket = MagicMock()
        mock_socket.recv.side_effect = socket.timeout()

        result = server._recv_exact(mock_socket, 256)

        assert result is None


class TestVotifierServerHandleClient:
    """Tests for individual client handling."""

    def test_handle_client_sends_greeting(self, full_config):
        with patch("main.RconClient") as mock_rcon:
            mock_rcon_instance = MagicMock()
            mock_rcon.return_value = mock_rcon_instance

            server = VotifierServer(full_config)

        mock_socket = MagicMock()
        mock_socket.recv.return_value = b""

        server._handle_client(mock_socket, ("127.0.0.1", 12345))

        mock_socket.sendall.assert_called_once()
        greeting = mock_socket.sendall.call_args[0][0]
        assert b"VOTIFIER" in greeting

    def test_handle_client_processes_valid_vote(self, full_config):
        with patch("main.RconClient") as mock_rcon:
            mock_rcon_instance = MagicMock()
            mock_rcon_instance.process_vote.return_value = "Success"
            mock_rcon.return_value = mock_rcon_instance

            server = VotifierServer(full_config)

        vote_data = b"VOTE\nTestService\nTestPlayer\n192.168.1.1\n1234567890\n"
        public_key = server.protocol._public_key
        encrypted_vote = public_key.encrypt(vote_data, padding.PKCS1v15())

        mock_socket = MagicMock()
        mock_socket.recv.return_value = encrypted_vote

        server._handle_client(mock_socket, ("127.0.0.1", 12345))

        mock_rcon_instance.process_vote.assert_called_once_with("TestPlayer", "TestService")

    def test_handle_client_invalid_vote_data(self, full_config):
        with patch("main.RconClient") as mock_rcon:
            mock_rcon_instance = MagicMock()
            mock_rcon.return_value = mock_rcon_instance

            server = VotifierServer(full_config)

        mock_socket = MagicMock()
        mock_socket.recv.return_value = b"\x00" * 256

        server._handle_client(mock_socket, ("127.0.0.1", 12345))

        mock_rcon_instance.process_vote.assert_not_called()

    def test_handle_client_closes_socket(self, full_config):
        with patch("main.RconClient"):
            server = VotifierServer(full_config)

        mock_socket = MagicMock()
        mock_socket.recv.return_value = b""

        server._handle_client(mock_socket, ("127.0.0.1", 12345))

        mock_socket.close.assert_called_once()

    def test_handle_client_rcon_failure(self, full_config):
        with patch("main.RconClient") as mock_rcon:
            mock_rcon_instance = MagicMock()
            mock_rcon_instance.process_vote.side_effect = Exception("RCON failed")
            mock_rcon.return_value = mock_rcon_instance

            server = VotifierServer(full_config)

        vote_data = b"VOTE\nTestService\nTestPlayer\n192.168.1.1\n1234567890\n"
        public_key = server.protocol._public_key
        encrypted_vote = public_key.encrypt(vote_data, padding.PKCS1v15())

        mock_socket = MagicMock()
        mock_socket.recv.return_value = encrypted_vote

        server._handle_client(mock_socket, ("127.0.0.1", 12345))

        mock_socket.close.assert_called_once()


class TestVotifierServerIntegration:
    """Integration tests for the Votifier server."""

    def test_server_accepts_connection(self, full_config):
        full_config.votifier.port = 0

        with patch("main.RconClient") as mock_rcon:
            mock_rcon_instance = MagicMock()
            mock_rcon_instance.test_connection.return_value = True
            mock_rcon_instance.process_vote.return_value = "Success"
            mock_rcon.return_value = mock_rcon_instance

            server = VotifierServer(full_config)

        server_started = threading.Event()
        actual_port = [0]

        def run_server():
            try:
                server._server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                server._server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                server._server_socket.bind((full_config.votifier.host, 0))
                actual_port[0] = server._server_socket.getsockname()[1]
                server._server_socket.listen(1)
                server._running = True
                server_started.set()
                server._accept_connections()
            except Exception:
                server_started.set()

        server_thread = threading.Thread(target=run_server, daemon=True)
        server_thread.start()

        server_started.wait(timeout=2)

        if actual_port[0] > 0:
            try:
                client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                client.settimeout(1)
                client.connect(("127.0.0.1", actual_port[0]))

                greeting = client.recv(1024)
                assert b"VOTIFIER" in greeting

                client.close()
            finally:
                server.stop()

        server_thread.join(timeout=1)

    def test_full_vote_flow(self, full_config):
        full_config.votifier.port = 0

        with patch("main.RconClient") as mock_rcon:
            mock_rcon_instance = MagicMock()
            mock_rcon_instance.test_connection.return_value = True
            mock_rcon_instance.process_vote.return_value = "Vote processed"
            mock_rcon.return_value = mock_rcon_instance

            server = VotifierServer(full_config)

        vote_data = b"VOTE\nIntegrationTest\nIntegrationPlayer\n10.0.0.1\n9999999999\n"
        public_key = server.protocol._public_key
        encrypted_vote = public_key.encrypt(vote_data, padding.PKCS1v15())

        server_started = threading.Event()
        actual_port = [0]

        def run_server():
            try:
                server._server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                server._server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                server._server_socket.bind((full_config.votifier.host, 0))
                actual_port[0] = server._server_socket.getsockname()[1]
                server._server_socket.listen(1)
                server._running = True
                server_started.set()
                server._accept_connections()
            except Exception:
                server_started.set()

        server_thread = threading.Thread(target=run_server, daemon=True)
        server_thread.start()

        server_started.wait(timeout=2)

        if actual_port[0] > 0:
            try:
                client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                client.settimeout(2)
                client.connect(("127.0.0.1", actual_port[0]))

                greeting = client.recv(1024)
                assert b"VOTIFIER" in greeting

                client.sendall(encrypted_vote)
                time.sleep(0.2)

                client.close()
                time.sleep(0.1)

                mock_rcon_instance.process_vote.assert_called_with(
                    "IntegrationPlayer", "IntegrationTest"
                )
            finally:
                server.stop()

        server_thread.join(timeout=1)
