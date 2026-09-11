"""Dépendances FastAPI : session de base et client Redis."""

from __future__ import annotations

from collections.abc import AsyncIterator

import redis.asyncio as aioredis
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import get_settings
from src.db.session import session_scope


async def session_db() -> AsyncIterator[AsyncSession]:
    """Session transactionnelle : commit en sortie normale, rollback sur exception."""
    async with session_scope() as session:
        yield session


async def cache_redis() -> AsyncIterator[aioredis.Redis]:
    """Client Redis fermé en fin de requête."""
    client: aioredis.Redis = aioredis.from_url(
        get_settings().redis_url, decode_responses=True
    )
    try:
        yield client
    finally:
        await client.aclose()
