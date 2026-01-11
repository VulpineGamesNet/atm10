"""Tests for Votifier protocol handling."""

import sys
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

sys.path.insert(0, str(Path(__file__).parent.parent))

from votifier_protocol import VOTIFIER_VERSION, Vote, VotifierProtocol


class TestVote:
    """Tests for Vote dataclass."""

    def test_create_vote(self):
        vote = Vote(
            service_name="PlanetMinecraft",
            username="TestPlayer",
            address="192.168.1.1",
            timestamp="1234567890",
        )
        assert vote.service_name == "PlanetMinecraft"
        assert vote.username == "TestPlayer"
        assert vote.address == "192.168.1.1"
        assert vote.timestamp == "1234567890"

    def test_vote_str(self):
        vote = Vote(
            service_name="TestService",
            username="Player",
            address="127.0.0.1",
            timestamp="123",
        )
        result = str(vote)
        assert "TestService" in result
        assert "Player" in result
        assert "127.0.0.1" in result
        assert "123" in result


class TestVotifierProtocolKeyManagement:
    """Tests for RSA key generation and loading."""

    def test_generates_keys_on_init(self, temp_keys_dir):
        protocol = VotifierProtocol(temp_keys_dir)

        private_key_path = Path(temp_keys_dir) / "private.pem"
        public_key_path = Path(temp_keys_dir) / "public.pem"

        assert private_key_path.exists()
        assert public_key_path.exists()

    def test_loads_existing_keys(self, temp_keys_dir):
        protocol1 = VotifierProtocol(temp_keys_dir)
        public_key_pem1 = protocol1.get_public_key_pem()

        protocol2 = VotifierProtocol(temp_keys_dir)
        public_key_pem2 = protocol2.get_public_key_pem()

        assert public_key_pem1 == public_key_pem2

    def test_get_public_key_pem_format(self, votifier_protocol):
        pem = votifier_protocol.get_public_key_pem()

        assert pem.startswith("-----BEGIN PUBLIC KEY-----")
        assert pem.strip().endswith("-----END PUBLIC KEY-----")

    def test_creates_keys_directory_if_not_exists(self, temp_keys_dir):
        nested_path = Path(temp_keys_dir) / "nested" / "keys"
        protocol = VotifierProtocol(str(nested_path))

        assert nested_path.exists()
        assert (nested_path / "private.pem").exists()
        assert (nested_path / "public.pem").exists()


class TestVotifierProtocolGreeting:
    """Tests for protocol greeting message."""

    def test_get_greeting(self, votifier_protocol):
        greeting = votifier_protocol.get_greeting()

        assert isinstance(greeting, bytes)
        assert greeting == f"VOTIFIER {VOTIFIER_VERSION}\n".encode()

    def test_greeting_contains_version(self, votifier_protocol):
        greeting = votifier_protocol.get_greeting().decode()

        assert "VOTIFIER" in greeting
        assert VOTIFIER_VERSION in greeting
        assert greeting.endswith("\n")


class TestVotifierProtocolVoteParsing:
    """Tests for vote data parsing."""

    def test_parse_valid_vote(self, votifier_protocol, sample_vote_data):
        vote = votifier_protocol.parse_vote(sample_vote_data)

        assert vote.service_name == "PlanetMinecraft"
        assert vote.username == "TestPlayer"
        assert vote.address == "192.168.1.1"
        assert vote.timestamp == "1234567890"

    def test_parse_vote_with_extra_whitespace(self, votifier_protocol):
        data = b"VOTE\n  ServiceName  \n  Player123  \n  10.0.0.1  \n  9999  \n"
        vote = votifier_protocol.parse_vote(data)

        assert vote.service_name == "ServiceName"
        assert vote.username == "Player123"
        assert vote.address == "10.0.0.1"
        assert vote.timestamp == "9999"

    def test_parse_vote_invalid_opcode(self, votifier_protocol):
        data = b"INVALID\nService\nPlayer\n127.0.0.1\n123\n"

        with pytest.raises(ValueError, match="Invalid opcode"):
            votifier_protocol.parse_vote(data)

    def test_parse_vote_too_few_lines(self, votifier_protocol):
        data = b"VOTE\nService\nPlayer\n"

        with pytest.raises(ValueError, match="expected 5 lines"):
            votifier_protocol.parse_vote(data)

    def test_parse_vote_invalid_encoding(self, votifier_protocol):
        data = b"\xff\xfe\x00\x01"

        with pytest.raises(ValueError, match="Failed to decode"):
            votifier_protocol.parse_vote(data)


class TestVotifierProtocolDecryption:
    """Tests for vote block decryption."""

    def test_decrypt_valid_block(self, votifier_protocol, sample_vote_data):
        public_key = votifier_protocol._public_key

        encrypted = public_key.encrypt(sample_vote_data, padding.PKCS1v15())
        decrypted = votifier_protocol.decrypt_vote_block(encrypted)

        assert decrypted == sample_vote_data

    def test_decrypt_invalid_block_size(self, votifier_protocol):
        with pytest.raises(ValueError, match="Invalid block size"):
            votifier_protocol.decrypt_vote_block(b"short")

    def test_decrypt_random_data_fails_or_produces_garbage(self, votifier_protocol):
        """Random data either fails to decrypt or produces unparseable garbage."""
        import secrets
        random_block = secrets.token_bytes(256)

        try:
            decrypted = votifier_protocol.decrypt_vote_block(random_block)
            assert not decrypted.startswith(b"VOTE\n")
        except ValueError:
            pass

    def test_decrypt_with_different_key_produces_garbage(self, temp_keys_dir, sample_vote_data):
        """Data encrypted with wrong key either fails or produces garbage."""
        protocol1 = VotifierProtocol(temp_keys_dir)

        different_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        encrypted = different_key.public_key().encrypt(sample_vote_data, padding.PKCS1v15())

        try:
            decrypted = protocol1.decrypt_vote_block(encrypted)
            assert decrypted != sample_vote_data
        except ValueError:
            pass


class TestVotifierProtocolProcessVoteBlock:
    """Tests for end-to-end vote block processing."""

    def test_process_vote_block_success(self, votifier_protocol, sample_vote_data):
        public_key = votifier_protocol._public_key
        encrypted = public_key.encrypt(sample_vote_data, padding.PKCS1v15())

        vote = votifier_protocol.process_vote_block(encrypted)

        assert isinstance(vote, Vote)
        assert vote.service_name == "PlanetMinecraft"
        assert vote.username == "TestPlayer"
        assert vote.address == "192.168.1.1"
        assert vote.timestamp == "1234567890"

    def test_process_vote_block_with_special_characters(self, votifier_protocol):
        vote_data = b"VOTE\nTest-Service_123\nPlayer_Name-Test\n::1\n1234567890\n"
        public_key = votifier_protocol._public_key
        encrypted = public_key.encrypt(vote_data, padding.PKCS1v15())

        vote = votifier_protocol.process_vote_block(encrypted)

        assert vote.service_name == "Test-Service_123"
        assert vote.username == "Player_Name-Test"
        assert vote.address == "::1"


class TestVotifierProtocolIntegration:
    """Integration tests for the full protocol flow."""

    def test_full_vote_flow(self, temp_keys_dir):
        server_protocol = VotifierProtocol(temp_keys_dir)

        greeting = server_protocol.get_greeting()
        assert b"VOTIFIER" in greeting

        public_key_pem = server_protocol.get_public_key_pem()
        public_key = serialization.load_pem_public_key(public_key_pem.encode())

        vote_data = b"VOTE\nMyVotingSite\nCoolPlayer\n192.168.0.100\n1609459200\n"
        encrypted = public_key.encrypt(vote_data, padding.PKCS1v15())

        vote = server_protocol.process_vote_block(encrypted)

        assert vote.service_name == "MyVotingSite"
        assert vote.username == "CoolPlayer"
        assert vote.address == "192.168.0.100"
        assert vote.timestamp == "1609459200"

    def test_multiple_votes_same_protocol(self, votifier_protocol):
        public_key = votifier_protocol._public_key

        votes_data = [
            b"VOTE\nSite1\nPlayer1\n1.1.1.1\n1000\n",
            b"VOTE\nSite2\nPlayer2\n2.2.2.2\n2000\n",
            b"VOTE\nSite3\nPlayer3\n3.3.3.3\n3000\n",
        ]

        for i, vote_data in enumerate(votes_data, 1):
            encrypted = public_key.encrypt(vote_data, padding.PKCS1v15())
            vote = votifier_protocol.process_vote_block(encrypted)

            assert vote.service_name == f"Site{i}"
            assert vote.username == f"Player{i}"
