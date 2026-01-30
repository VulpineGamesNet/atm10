"""Votifier service main entry point - TCP server for receiving votes."""

import logging
import signal
import socket
import sys
import threading
import time
from typing import Optional

from config import Config, load_config
from pending_rewards import pending_store, vote_dedup
from rcon_client import RconClient
from votifier_protocol import VotifierProtocol

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


class VotifierServer:
    """TCP server that handles Votifier protocol connections."""

    CLAIM_POLL_INTERVAL = 1.0  # Poll claim queue every 1 second
    PLAYER_POLL_INTERVAL = 5.0  # Poll online players every 5 seconds

    def __init__(self, config: Config) -> None:
        """
        Initialize the Votifier server.

        Args:
            config: Server configuration
        """
        self.config = config
        self.protocol = VotifierProtocol(config.votifier.keys_path)
        self.rcon = RconClient(config.rcon)
        self._server_socket: Optional[socket.socket] = None
        self._running = False
        self._poll_thread: Optional[threading.Thread] = None
        self._player_poll_thread: Optional[threading.Thread] = None
        self._online_players: set[str] = set()  # Track online players
        self._notified_players: set[str] = set()  # Track players already notified about pending rewards

        if config.debug:
            logging.getLogger().setLevel(logging.DEBUG)

    def start(self) -> None:
        """Start the Votifier server."""
        self._server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

        try:
            self._server_socket.bind((self.config.votifier.host, self.config.votifier.port))
            self._server_socket.listen(5)
            self._running = True

            logger.info(
                f"Votifier server listening on {self.config.votifier.host}:{self.config.votifier.port}"
            )
            logger.info("Public key for voting sites:")
            logger.info(self.protocol.get_public_key_pem())

            # Test RCON connection
            if self.rcon.test_connection():
                logger.info("RCON connection verified")
            else:
                logger.warning("RCON connection failed - will retry when needed")

            # Start claim queue polling (will reconnect if needed)
            self._start_claim_polling()
            # Start player join polling for pending rewards notification
            self._start_player_polling()

            self._accept_connections()

        except Exception as e:
            logger.error(f"Failed to start server: {e}")
            raise
        finally:
            self.stop()

    def stop(self) -> None:
        """Stop the Votifier server."""
        self._running = False
        if self._poll_thread and self._poll_thread.is_alive():
            self._poll_thread.join(timeout=2.0)
        if self._player_poll_thread and self._player_poll_thread.is_alive():
            self._player_poll_thread.join(timeout=2.0)
        if self._server_socket:
            try:
                self._server_socket.close()
            except Exception:
                pass
            self._server_socket = None
        self.rcon.close()
        logger.info("Votifier server stopped")

    def _start_claim_polling(self) -> None:
        """Start the claim queue polling thread."""
        self._poll_thread = threading.Thread(target=self._poll_claim_queue, daemon=True)
        self._poll_thread.start()
        logger.info("Claim queue polling started")

    def _poll_claim_queue(self) -> None:
        """Poll for claim requests every interval."""
        while self._running:
            try:
                response = self.rcon.execute("kubevote claimqueue")
                if response and "CLAIMQUEUE:" in response:
                    queue_data = response.split("CLAIMQUEUE:")[1].strip()
                    if queue_data:
                        usernames = queue_data.split(",")
                        for username in usernames:
                            username = username.strip()
                            if username:
                                logger.info(f"Processing claim request for {username}")
                                self.claim_pending_rewards(username)
            except Exception as e:
                logger.debug(f"Claim queue poll failed: {e}")
            time.sleep(self.CLAIM_POLL_INTERVAL)

    def _start_player_polling(self) -> None:
        """Start the player join polling thread."""
        self._player_poll_thread = threading.Thread(target=self._poll_online_players, daemon=True)
        self._player_poll_thread.start()
        logger.info("Player join polling started")

    def _poll_online_players(self) -> None:
        """Poll online players and notify new joins with pending rewards."""
        while self._running:
            try:
                response = self.rcon.execute("list")
                if not response:
                    time.sleep(self.PLAYER_POLL_INTERVAL)
                    continue

                current_players = self._parse_player_list(response)

                # Don't update if parse returned empty but we had players before
                # (likely a parsing failure, not everyone logging off)
                if not current_players and self._online_players:
                    time.sleep(self.PLAYER_POLL_INTERVAL)
                    continue

                # Clear notification flag for players who logged off
                logged_off = self._online_players - current_players
                for player in logged_off:
                    self._notified_players.discard(player.lower())

                # Find newly joined players
                new_players = current_players - self._online_players

                for player in new_players:
                    # Skip if already notified this session
                    if player.lower() in self._notified_players:
                        continue
                    count = pending_store.get_pending_count(player)
                    if count > 0:
                        logger.info(f"Player {player} joined with {count} pending rewards")
                        self._notify_pending_rewards(player, count)
                        self._notified_players.add(player.lower())

                self._online_players = current_players

            except Exception as e:
                logger.debug(f"Player poll failed: {e}")
            time.sleep(self.PLAYER_POLL_INTERVAL)

    def _parse_player_list(self, response: str) -> set[str]:
        """Parse the list command response to extract player names."""
        # Format: "There are X of a max of Y players online: Player1, Player2"
        # Or: "There are 0 of a max of Y players online:"
        players: set[str] = set()
        if not response or ":" not in response:
            return players

        parts = response.split(":")
        if len(parts) < 2:
            return players

        player_part = parts[-1].strip()
        if not player_part:
            return players

        for name in player_part.split(","):
            name = name.strip()
            if name:
                # Strip rank prefixes like [ADM], [MOD], etc.
                if "]" in name:
                    name = name.split("]")[-1].strip()
                players.add(name)

        return players

    def _notify_pending_rewards(self, username: str, count: int) -> None:
        """Send a pretty message to player about pending rewards."""
        try:
            # Use tellraw for pretty JSON message
            msg = (
                '["",{"text":"★ ","color":"gold"},'
                '{"text":"Vote Rewards Available","color":"yellow"},'
                '{"text":" ★\\n","color":"gold"},'
                '{"text":"  You have ","color":"gray"},'
                f'{{"text":"{count}","color":"green"}},'
                '{"text":" pending vote reward' + ('s' if count != 1 else '') + '!\\n","color":"gray"},'
                '{"text":"  Use ","color":"gray"},'
                '{"text":"/vote claim","color":"aqua","clickEvent":{"action":"run_command","value":"/vote claim"}},'
                '{"text":" to collect them.","color":"gray"}]'
            )
            self.rcon.execute(f'tellraw {username} {msg}')
        except Exception as e:
            logger.error(f"Failed to notify {username} about pending rewards: {e}")

    def claim_pending_rewards(self, username: str) -> bool:
        """
        Claim pending rewards for a player.

        Args:
            username: Player username to claim rewards for

        Returns:
            True if rewards were claimed, False otherwise
        """
        count = pending_store.get_pending_count(username)

        try:
            # Always call RCON so player gets feedback (even if count=0)
            response = self.rcon.claim_pending_rewards(username, count)
            logger.info(f"Claim response for {username} (count={count}): {response}")

            if count > 0:
                # Mark rewards as claimed
                pending_store.claim_all(username)
                # Clean up claimed rewards
                pending_store.clear_claimed(username)
                # Clear notification flag so they can be notified of future rewards
                self._notified_players.discard(username.lower())
            return count > 0
        except Exception as e:
            logger.error(f"Failed to claim pending rewards for {username}: {e}")
            return False

    def _accept_connections(self) -> None:
        """Accept and handle incoming connections."""
        while self._running:
            try:
                if self._server_socket is None:
                    break

                self._server_socket.settimeout(1.0)

                try:
                    client_socket, client_address = self._server_socket.accept()
                except socket.timeout:
                    continue

                logger.info(f"Connection from {client_address}")

                thread = threading.Thread(
                    target=self._handle_client,
                    args=(client_socket, client_address),
                    daemon=True,
                )
                thread.start()

            except Exception as e:
                if self._running:
                    logger.error(f"Error accepting connection: {e}")

    def _handle_client(self, client_socket: socket.socket, client_address: tuple) -> None:
        """
        Handle a single client connection.

        Args:
            client_socket: Connected client socket
            client_address: Client address tuple (host, port)
        """
        try:
            client_socket.settimeout(5.0)

            # Send Votifier greeting
            greeting = self.protocol.get_greeting()
            client_socket.sendall(greeting)
            logger.debug(f"Sent greeting to {client_address}")

            # Receive 256-byte encrypted block
            encrypted_block = self._recv_exact(client_socket, 256)
            if encrypted_block is None:
                logger.warning(f"Failed to receive vote block from {client_address}")
                return

            logger.debug(f"Received {len(encrypted_block)} bytes from {client_address}")

            # Process the vote
            try:
                vote = self.protocol.process_vote_block(encrypted_block)
                logger.info(f"Received vote: {vote}")

                # Check for duplicate vote (1-hour dedup window)
                if vote_dedup.is_duplicate(vote.username, vote.service_name):
                    logger.info(
                        f"Duplicate vote rejected: {vote.username} for {vote.service_name}"
                    )
                    return

                # Mark vote as processed
                vote_dedup.mark_processed(vote.username, vote.service_name)

                # Send vote to Minecraft via RCON
                try:
                    response = self.rcon.process_vote(vote.username, vote.service_name)
                    logger.info(f"RCON response: {response}")

                    # Check if player was offline (response indicates failure)
                    if "not found" in response.lower() or "no player" in response.lower():
                        logger.info(f"Player {vote.username} is offline, saving pending reward")
                        pending_store.add_pending(vote.username, vote.service_name)
                except Exception as e:
                    logger.error(f"Failed to process vote via RCON: {e}")
                    # Save as pending reward on RCON failure
                    logger.info(f"Saving pending reward for {vote.username} due to RCON failure")
                    pending_store.add_pending(vote.username, vote.service_name)

            except ValueError as e:
                logger.error(f"Failed to process vote from {client_address}: {e}")

        except socket.timeout:
            logger.warning(f"Timeout handling client {client_address}")
        except Exception as e:
            logger.error(f"Error handling client {client_address}: {e}")
        finally:
            try:
                client_socket.close()
            except Exception:
                pass

    def _recv_exact(self, sock: socket.socket, size: int) -> Optional[bytes]:
        """
        Receive exactly `size` bytes from socket.

        Args:
            sock: Socket to receive from
            size: Exact number of bytes to receive

        Returns:
            Received bytes or None if failed
        """
        data = b""
        while len(data) < size:
            try:
                chunk = sock.recv(size - len(data))
                if not chunk:
                    return None
                data += chunk
            except socket.timeout:
                return None
        return data


def main() -> None:
    """Main entry point."""
    logger.info("Starting Votifier service...")

    try:
        config = load_config()
    except ValueError as e:
        logger.error(f"Configuration error: {e}")
        sys.exit(1)

    server = VotifierServer(config)

    def signal_handler(signum: int, frame) -> None:
        logger.info(f"Received signal {signum}, shutting down...")
        server.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        server.start()
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    except Exception as e:
        logger.error(f"Server error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
