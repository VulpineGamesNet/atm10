"""Database manager for Discord-Minecraft chat sync."""

import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.future import select

from config import DatabaseConfig
from models import Base, DiscordEvent

logger = logging.getLogger("discord_mc_bot.database")


class DatabaseManager:
    """Manages async database connections and operations."""

    def __init__(self, config: DatabaseConfig):
        self.config = config
        self._engine = create_async_engine(
            config.async_url,
            pool_size=5,
            max_overflow=10,
            pool_recycle=3600,
            echo=False,
        )
        self._session_factory = async_sessionmaker(
            self._engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )
        self._initialized = False

    async def initialize(self) -> bool:
        """Initialize database connection and verify connectivity."""
        try:
            async with self._engine.begin() as conn:
                # Verify connection by running a simple query
                await conn.run_sync(lambda _: None)
            self._initialized = True
            logger.info(f"Database connected: {self.config.host}:{self.config.port}/{self.config.database}")
            return True
        except Exception as e:
            logger.error(f"Failed to connect to database: {e}")
            self._initialized = False
            return False

    async def close(self) -> None:
        """Close database connection pool."""
        if self._engine:
            await self._engine.dispose()
            logger.info("Database connection closed")

    @property
    def is_initialized(self) -> bool:
        """Check if database is initialized."""
        return self._initialized

    async def get_unprocessed_events(self, limit: int = 10) -> list[DiscordEvent]:
        """Fetch unprocessed events from database."""
        if not self._initialized:
            return []

        try:
            async with self._session_factory() as session:
                stmt = (
                    select(DiscordEvent)
                    .where(DiscordEvent.processed_at.is_(None))
                    .order_by(DiscordEvent.created_at)
                    .limit(limit)
                )
                result = await session.execute(stmt)
                return list(result.scalars().all())
        except Exception as e:
            logger.error(f"Error fetching unprocessed events: {e}")
            return []

    async def mark_events_processed(self, event_ids: list[int]) -> bool:
        """Mark events as processed."""
        if not self._initialized or not event_ids:
            return False

        try:
            async with self._session_factory() as session:
                stmt = (
                    update(DiscordEvent)
                    .where(DiscordEvent.id.in_(event_ids))
                    .values(processed_at=datetime.now(timezone.utc))
                )
                await session.execute(stmt)
                await session.commit()
                logger.debug(f"Marked {len(event_ids)} events as processed")
                return True
        except Exception as e:
            logger.error(f"Error marking events as processed: {e}")
            return False
