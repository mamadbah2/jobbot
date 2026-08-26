"""Process `worker_ingest` : scraping des offres toutes les 2 h (CLAUDE.md §4).

Phase 0 : la boucle tourne à vide. Le pipeline arrive en Phase 1.
"""

from __future__ import annotations

import asyncio
import contextlib

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from src.config import get_settings
from src.db.session import dispose_engine
from src.logging_setup import get_logger, setup_logging

log = get_logger(__name__)

INTERVALLE_HEURES = 2


async def ingerer() -> None:
    """Cycle d'ingestion. Corps implémenté en Phase 1."""
    log.info("ingestion_cycle", statut="ignore", raison="phase_1_non_implementee")


async def main() -> None:
    settings = get_settings()
    setup_logging(settings.log_level, json_output=settings.is_prod)

    scheduler = AsyncIOScheduler(timezone="UTC")
    scheduler.add_job(
        ingerer,
        IntervalTrigger(hours=INTERVALLE_HEURES),
        id="ingestion",
        max_instances=1,
        coalesce=True,
    )
    scheduler.start()
    log.info("demarrage_worker", worker="ingest", intervalle_heures=INTERVALLE_HEURES)

    try:
        await asyncio.Event().wait()
    finally:
        scheduler.shutdown(wait=False)
        await dispose_engine()


if __name__ == "__main__":
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(main())
