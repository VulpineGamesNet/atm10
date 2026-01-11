"""RCON client for communicating with Minecraft server."""

import logging

from mcrcon import MCRcon

from config import RconConfig

logger = logging.getLogger(__name__)


class RconClient:
    """Client for executing commands on Minecraft server via RCON."""

    def __init__(self, config: RconConfig) -> None:
        """
        Initialize RCON client.

        Args:
            config: RCON configuration with host, port, and password
        """
        self.config = config

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
            with MCRcon(
                host=self.config.host,
                password=self.config.password,
                port=self.config.port,
                timeout=None,  # Disable signal-based timeout for thread safety
            ) as mcr:
                response = mcr.command(command)
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
        command = f"kubevote process {username} {service}"
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
