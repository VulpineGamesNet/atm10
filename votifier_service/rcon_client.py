"""RCON client for communicating with Minecraft server - socket-based, no signals."""

import logging
import socket
import struct

from config import RconConfig

logger = logging.getLogger(__name__)

RCON_SERVERDATA_AUTH = 3
RCON_SERVERDATA_EXECCOMMAND = 2


class RconClient:
    """Client for executing commands on Minecraft server via RCON."""

    def __init__(self, config: RconConfig) -> None:
        """
        Initialize RCON client.

        Args:
            config: RCON configuration with host, port, and password
        """
        self.config = config

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

    def execute(self, command: str) -> str:
        """
        Execute a command on the Minecraft server.

        Args:
            command: The command to execute (without leading /)

        Returns:
            Server response string

        Raises:
            Exception: If connection or command execution fails
        """
        logger.debug(f"Executing RCON command: {command}")

        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(10.0)
            sock.connect((self.config.host, self.config.port))

            # Authenticate
            self._send_packet(sock, 1, RCON_SERVERDATA_AUTH, self.config.password)
            packet_id, _, _ = self._recv_packet(sock)

            if packet_id == -1:
                sock.close()
                raise ConnectionError("RCON authentication failed - check password")

            # Send command
            self._send_packet(sock, 2, RCON_SERVERDATA_EXECCOMMAND, command)
            _, _, response = self._recv_packet(sock)

            sock.close()
            logger.debug(f"RCON response: {response}")
            return response

        except Exception as e:
            logger.error(f"RCON command failed: {e}")
            raise

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
