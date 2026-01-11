"""RCON client for communicating with Minecraft server - persistent connection."""

import logging
import socket
import struct
from typing import Optional

from config import RconConfig

logger = logging.getLogger(__name__)

RCON_SERVERDATA_AUTH = 3
RCON_SERVERDATA_EXECCOMMAND = 2


class RconClient:
    """Client for executing commands on Minecraft server via RCON with persistent connection."""

    def __init__(self, config: RconConfig) -> None:
        """
        Initialize RCON client.

        Args:
            config: RCON configuration with host, port, and password
        """
        self.config = config
        self._socket: Optional[socket.socket] = None
        self._connected: bool = False

    def _send_packet(
        self, sock: socket.socket, packet_id: int, packet_type: int, payload: str
    ) -> None:
        """Send an RCON packet."""
        payload_bytes = payload.encode("utf-8") + b"\x00\x00"
        packet = struct.pack("<ii", packet_id, packet_type) + payload_bytes
        packet = struct.pack("<i", len(packet)) + packet
        sock.sendall(packet)

    def _recv_packet(self, sock: socket.socket) -> tuple[int, int, str]:
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

    def _connect(self) -> bool:
        """Establish persistent RCON connection with authentication."""
        self._disconnect()

        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(10.0)
            sock.connect((self.config.host, self.config.port))

            self._send_packet(sock, 1, RCON_SERVERDATA_AUTH, self.config.password)
            packet_id, _, _ = self._recv_packet(sock)

            if packet_id == -1:
                logger.error("RCON authentication failed - check password")
                sock.close()
                return False

            sock.settimeout(30.0)
            self._socket = sock
            self._connected = True
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

    def _disconnect(self) -> None:
        """Close RCON connection cleanly."""
        if self._socket:
            try:
                self._socket.close()
            except OSError:
                pass
            self._socket = None
        self._connected = False

    def close(self) -> None:
        """Close the RCON connection (public interface for cleanup)."""
        self._disconnect()
        logger.debug("RCON client closed")

    def execute(self, command: str) -> str:
        """
        Execute a command on the Minecraft server using persistent connection.

        Args:
            command: The command to execute (without leading /)

        Returns:
            Server response string

        Raises:
            ConnectionError: If connection or command execution fails
        """
        logger.debug(f"Executing RCON command: {command}")

        if not self._connected:
            if not self._connect():
                raise ConnectionError("Failed to connect to RCON")

        try:
            self._send_packet(self._socket, 2, RCON_SERVERDATA_EXECCOMMAND, command)
            _, _, response = self._recv_packet(self._socket)
            logger.debug(f"RCON response: {response}")
            return response

        except (socket.timeout, socket.error, ConnectionError, BrokenPipeError, OSError) as e:
            logger.warning(f"RCON command failed, connection lost: {e}")
            self._disconnect()
            raise ConnectionError(f"RCON disconnected: {e}")

    def process_vote(self, username: str, service: str) -> str:
        """
        Process a vote by executing the kubevote command.

        Args:
            username: Player who voted
            service: Voting site service name

        Returns:
            Server response
        """
        # Sanitize service name - replace spaces with underscores
        service_sanitized = service.replace(" ", "_")
        command = f"kubevote process {username} {service_sanitized}"
        return self.execute(command)

    def test_connection(self) -> bool:
        """
        Test the RCON connection.

        Returns:
            True if connection successful, False otherwise
        """
        try:
            response = self.execute("list")
            logger.info(f"RCON connection test successful: {response}")
            return True
        except Exception as e:
            logger.error(f"RCON connection test failed: {e}")
            return False
