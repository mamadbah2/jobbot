"""Healthcheck : Postgres + Redis. Déplacé depuis `src/health.py` le 2026-09-11,
quand le process `api` a remplacé le serveur HTTP monté dans le bot (CLAUDE.md §4).
"""

from __future__ import annotations

from typing import Any

import redis.asyncio as aioredis
from fastapi import APIRouter, Response, status
from sqlalchemy import text

from src.config import get_settings
from src.db.session import get_engine
from src.logging_setup import get_logger

log = get_logger(__name__)
router = APIRouter(tags=["sante"])


@router.get("/health")
async def health(response: Response) -> dict[str, Any]:
    """Vérifie Postgres et Redis. 503 si l'un des deux est indisponible."""
    checks: dict[str, str] = {}

    try:
        async with get_engine().connect() as conn:
            await conn.execute(text("SELECT 1"))
        checks["postgres"] = "ok"
    except Exception as exc:  # noqa: BLE001 — le healthcheck ne doit jamais lever
        checks["postgres"] = "erreur"
        log.warning("healthcheck_postgres_ko", error=str(exc))

    client = aioredis.from_url(get_settings().redis_url)
    try:
        await client.ping()
        checks["redis"] = "ok"
    except Exception as exc:  # noqa: BLE001
        checks["redis"] = "erreur"
        log.warning("healthcheck_redis_ko", error=str(exc))
    finally:
        await client.aclose()

    healthy = all(v == "ok" for v in checks.values())
    if not healthy:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return {"status": "ok" if healthy else "degraded", "checks": checks}
