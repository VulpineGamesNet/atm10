"""Pending rewards storage for offline players and vote deduplication."""

import json
import logging
import threading
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

DATA_DIR = Path("data")
PENDING_FILE = DATA_DIR / "pending_rewards.json"


@dataclass
class PendingReward:
    """A pending reward for an offline player."""
    username: str
    service: str
    timestamp: str
    claimed: bool = False


class PendingRewardsStore:
    """Thread-safe storage for pending rewards."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._rewards: dict[str, list[dict]] = {}
        self._load()

    def _load(self) -> None:
        """Load pending rewards from file."""
        try:
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            if PENDING_FILE.exists():
                with open(PENDING_FILE, "r") as f:
                    self._rewards = json.load(f)
                logger.info(f"Loaded pending rewards for {len(self._rewards)} players")
            else:
                self._rewards = {}
                logger.info("No pending rewards file found, starting fresh")
        except Exception as e:
            logger.error(f"Failed to load pending rewards: {e}")
            self._rewards = {}

    def _save(self) -> None:
        """Save pending rewards to file."""
        try:
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            with open(PENDING_FILE, "w") as f:
                json.dump(self._rewards, f, indent=2)
            logger.debug("Saved pending rewards")
        except Exception as e:
            logger.error(f"Failed to save pending rewards: {e}")

    def add_pending(self, username: str, service: str) -> None:
        """Add a pending reward for a player."""
        with self._lock:
            username_lower = username.lower()
            if username_lower not in self._rewards:
                self._rewards[username_lower] = []

            reward = PendingReward(
                username=username,
                service=service,
                timestamp=datetime.utcnow().isoformat(),
            )
            self._rewards[username_lower].append(asdict(reward))
            self._save()
            logger.info(f"Added pending reward for {username} from {service}")

    def get_pending(self, username: str) -> list[dict]:
        """Get all pending rewards for a player."""
        with self._lock:
            username_lower = username.lower()
            rewards = self._rewards.get(username_lower, [])
            # Return only unclaimed rewards
            return [r for r in rewards if not r.get("claimed", False)]

    def get_pending_count(self, username: str) -> int:
        """Get count of pending rewards for a player."""
        return len(self.get_pending(username))

    def claim_all(self, username: str) -> list[dict]:
        """Mark all pending rewards as claimed and return them."""
        with self._lock:
            username_lower = username.lower()
            rewards = self._rewards.get(username_lower, [])
            unclaimed = [r for r in rewards if not r.get("claimed", False)]

            # Mark as claimed
            for r in rewards:
                r["claimed"] = True

            self._save()
            logger.info(f"Claimed {len(unclaimed)} rewards for {username}")
            return unclaimed

    def clear_claimed(self, username: str) -> None:
        """Remove claimed rewards for a player."""
        with self._lock:
            username_lower = username.lower()
            if username_lower in self._rewards:
                self._rewards[username_lower] = [
                    r for r in self._rewards[username_lower]
                    if not r.get("claimed", False)
                ]
                if not self._rewards[username_lower]:
                    del self._rewards[username_lower]
                self._save()

    def get_all_pending_players(self) -> list[str]:
        """Get list of all players with pending rewards."""
        with self._lock:
            return [
                username for username, rewards in self._rewards.items()
                if any(not r.get("claimed", False) for r in rewards)
            ]


class VoteDeduplication:
    """Track recent votes to prevent duplicates within 1-hour window."""

    DEDUP_WINDOW_SECONDS = 3600  # 1 hour

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._votes: dict[str, float] = {}  # "username:service" -> timestamp

    def _make_key(self, username: str, service: str) -> str:
        return f"{username.lower()}:{service.lower()}"

    def is_duplicate(self, username: str, service: str) -> bool:
        """Check if vote is a duplicate within the dedup window."""
        key = self._make_key(username, service)
        now = time.time()
        with self._lock:
            self._cleanup_old_entries(now)
            return key in self._votes

    def mark_processed(self, username: str, service: str) -> None:
        """Mark a vote as processed."""
        key = self._make_key(username, service)
        with self._lock:
            self._votes[key] = time.time()

    def _cleanup_old_entries(self, now: float) -> None:
        """Remove entries older than dedup window."""
        cutoff = now - self.DEDUP_WINDOW_SECONDS
        self._votes = {k: v for k, v in self._votes.items() if v > cutoff}


# Global instances
pending_store = PendingRewardsStore()
vote_dedup = VoteDeduplication()
