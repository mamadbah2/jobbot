"""Process `worker_match` : matching + alertes, 2x/jour à 8h et 18h UTC (CLAUDE.md §4).

Phase 0 : la boucle tourne à vide. Le matching arrive en Phase 3.
"""

from __future__ import annotations

import asyncio
import contextlib

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from src.config import get_settings
from src.db.session import dispose_engine
from src.logging_setup import get_logger, setup_logging

log = get_logger(__name__)

HEURES_ENVOI = "8,18"


async def envoyer_alertes() -> None:
    """Cycle de matching et d'envoi des alertes. Corps implémenté en Phase 3."""
    log.info("matching_cycle", statut="ignore", raison="phase_3_non_implementee")


async def main() -> None:
    settings = get_settings()
    setup_logging(settings.log_level, json_output=settings.is_prod)

    scheduler = AsyncIOScheduler(timezone="UTC")
    scheduler.add_job(
        envoyer_alertes,
        CronTrigger(hour=HEURES_ENVOI, minute=0, timezone="UTC"),
        id="matching",
        max_instances=1,
        coalesce=True,
    )
    scheduler.start()
    log.info("demarrage_worker", worker="match", heures_utc=HEURES_ENVOI)

    try:
        await asyncio.Event().wait()
    finally:
        scheduler.shutdown(wait=False)
        await dispose_engine()


if __name__ == "__main__":
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(main())
