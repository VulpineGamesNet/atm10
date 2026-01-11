"""Votifier protocol implementation with RSA encryption handling."""

import logging
import os
from dataclasses import dataclass
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

logger = logging.getLogger(__name__)

VOTIFIER_VERSION = "2.0"


@dataclass
class Vote:
    """Represents a vote received from a voting site."""

    service_name: str
    username: str
    address: str
    timestamp: str

    def __str__(self) -> str:
        return f"Vote(service={self.service_name}, user={self.username}, addr={self.address}, time={self.timestamp})"


class VotifierProtocol:
    """Handles Votifier protocol RSA encryption and vote parsing."""

    def __init__(self, keys_path: str) -> None:
        """
        Initialize the Votifier protocol handler.

        Args:
            keys_path: Directory path where RSA keys are stored/generated
        """
        self.keys_path = Path(keys_path)
        self.keys_path.mkdir(parents=True, exist_ok=True)

        self.private_key_path = self.keys_path / "private.pem"
        self.public_key_path = self.keys_path / "public.pem"

        self._private_key: rsa.RSAPrivateKey | None = None
        self._public_key: rsa.RSAPublicKey | None = None

        self._load_or_generate_keys()

    def _load_or_generate_keys(self) -> None:
        """Load existing RSA keys or generate new ones if they don't exist."""
        if self.private_key_path.exists() and self.public_key_path.exists():
            self._load_keys()
        else:
            self._generate_keys()

    def _generate_keys(self) -> None:
        """Generate a new RSA key pair (2048-bit)."""
        logger.info("Generating new RSA key pair...")

        self._private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048,
        )
        self._public_key = self._private_key.public_key()

        private_pem = self._private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )

        public_pem = self._public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )

        self.private_key_path.write_bytes(private_pem)
        self.public_key_path.write_bytes(public_pem)

        logger.info(f"RSA keys saved to {self.keys_path}")
        logger.info("=" * 60)
        logger.info("PUBLIC KEY (configure this on voting sites):")
        logger.info("=" * 60)
        logger.info(public_pem.decode())
        logger.info("=" * 60)

    def _load_keys(self) -> None:
        """Load existing RSA keys from files."""
        logger.info(f"Loading RSA keys from {self.keys_path}")

        private_pem = self.private_key_path.read_bytes()
        self._private_key = serialization.load_pem_private_key(
            private_pem,
            password=None,
        )
        self._public_key = self._private_key.public_key()

        logger.info("RSA keys loaded successfully")

    def get_public_key_pem(self) -> str:
        """Get the public key in PEM format for voting site configuration."""
        if self._public_key is None:
            raise RuntimeError("Keys not initialized")

        public_pem = self._public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        return public_pem.decode()

    def decrypt_vote_block(self, encrypted_block: bytes) -> bytes:
        """
        Decrypt a 256-byte RSA encrypted vote block.

        Args:
            encrypted_block: The 256-byte encrypted data from voting site

        Returns:
            Decrypted vote data

        Raises:
            ValueError: If decryption fails
        """
        if self._private_key is None:
            raise RuntimeError("Keys not initialized")

        if len(encrypted_block) != 256:
            raise ValueError(f"Invalid block size: expected 256, got {len(encrypted_block)}")

        try:
            decrypted = self._private_key.decrypt(
                encrypted_block,
                padding.PKCS1v15(),
            )
            return decrypted
        except Exception as e:
            raise ValueError(f"Failed to decrypt vote block: {e}") from e

    def parse_vote(self, decrypted_data: bytes) -> Vote:
        """
        Parse decrypted vote data into a Vote object.

        Expected format:
            VOTE\n
            <service_name>\n
            <username>\n
            <address>\n
            <timestamp>\n

        Args:
            decrypted_data: Decrypted vote data bytes

        Returns:
            Vote object with parsed data

        Raises:
            ValueError: If vote data is malformed
        """
        try:
            data_str = decrypted_data.decode("utf-8")
            lines = data_str.strip().split("\n")

            if len(lines) < 5:
                raise ValueError(f"Invalid vote format: expected 5 lines, got {len(lines)}")

            opcode = lines[0].strip()
            if opcode != "VOTE":
                raise ValueError(f"Invalid opcode: expected 'VOTE', got '{opcode}'")

            return Vote(
                service_name=lines[1].strip(),
                username=lines[2].strip(),
                address=lines[3].strip(),
                timestamp=lines[4].strip(),
            )
        except UnicodeDecodeError as e:
            raise ValueError(f"Failed to decode vote data: {e}") from e

    def process_vote_block(self, encrypted_block: bytes) -> Vote:
        """
        Decrypt and parse a vote block in one step.

        Args:
            encrypted_block: The 256-byte encrypted data

        Returns:
            Parsed Vote object
        """
        decrypted = self.decrypt_vote_block(encrypted_block)
        return self.parse_vote(decrypted)

    def get_greeting(self) -> bytes:
        """Get the Votifier protocol greeting message."""
        return f"VOTIFIER {VOTIFIER_VERSION}\n".encode()
