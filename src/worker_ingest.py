"""Process `worker_ingest` : scraping des offres toutes les 2 h (CLAUDE.md §4).

Une passe, par source : lecture du `robots.txt`, pagination incrémentale
alimentée par les offres déjà en base, ouverture des seules annonces
nouvelles, puis écriture. Toute anomalie est journalisée ET remontée à
l'administrateur — §7 : « ne jamais échouer en silence ».
"""

from __future__ import annotations

import asyncio
import contextlib
import time
from dataclasses import asdict, dataclass
from typing import Final

import httpx
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from src.alerting import AlerteAdmin, construire_alerte
from src.config import Settings, get_settings
from src.db.session import dispose_engine, session_scope
from src.ingest.base import (
    BaseScraper,
    PoliteClient,
    StructureInattendueError,
    scraper_semble_casse,
)
from src.ingest.sources.emploidakar import EmploiDakarScraper
from src.ingest.store import DepotOffres, DepotSql
from src.logging_setup import get_logger, setup_logging

log = get_logger(__name__)

INTERVALLE_HEURES = 2

# Sources ingérées, dans l'ordre de priorité de §7.
SOURCES: Final[tuple[type[BaseScraper], ...]] = (EmploiDakarScraper,)

# Une annonce lente ne doit pas bloquer la passe entière.
TIMEOUT_HTTP = 30.0


@dataclass(frozen=True, slots=True)
class BilanSource:
    """Ce qu'une passe a fait sur une source, tel que journalisé."""

    source: str
    offres_vues: int
    nouvelles: int
    ecrites: int
    ignorees: int
    # Part des annonces portant un email de candidature : chiffre demandé par
    # §7 pour savoir si la source alimente l'auto-submit ou seulement le
    # mode brouillon. À remonter au porteur du projet.
    avec_email: int
    pages: int
    bloquee: bool
    casse: bool


def construire_client(classe: type[BaseScraper], settings: Settings) -> PoliteClient:
    """Client HTTP poli, propre à une source (§2, interdiction n°4)."""
    return PoliteClient(
        httpx.AsyncClient(timeout=TIMEOUT_HTTP, follow_redirects=True),
        user_agent=settings.scraper_user_agent,
        delai=settings.scraper_delay_seconds,
        horloge=time.monotonic,
        dormir=asyncio.sleep,
        # Plancher : tient même si le robots.txt du site est injoignable (§7).
        chemins_interdits=classe.chemins_interdits,
    )


async def ingerer_source(
    scraper: BaseScraper, depot: DepotOffres, alerte: AlerteAdmin
) -> BilanSource:
    """Passe complète sur une source, puis écriture des nouveautés."""
    ids_connus = await depot.ids_connus(scraper.source)

    try:
        resultat = await scraper.collecter(ids_connus)
    except StructureInattendueError as exc:
        # Le site a changé de structure : ce qu'on lirait encore serait faux,
        # donc rien n'est écrit et l'admin est prévenu (§7).
        log.error("structure_inattendue", source=scraper.source, erreur=str(exc))
        await alerte.envoyer("structure_inattendue", source=scraper.source, erreur=str(exc))
        return BilanSource(
            source=scraper.source,
            offres_vues=0,
            nouvelles=0,
            ecrites=0,
            ignorees=0,
            avec_email=0,
            pages=0,
            bloquee=False,
            casse=True,
        )

    # Ce qui a été lu avant l'incident est conservé : ces offres sont valides.
    ecriture = await depot.enregistrer(resultat.offres)

    casse = scraper_semble_casse(
        offres_vues=resultat.offres_vues, offres_connues=len(ids_connus)
    )
    bilan = BilanSource(
        source=scraper.source,
        offres_vues=resultat.offres_vues,
        nouvelles=len(resultat.offres),
        ecrites=ecriture.ecrites,
        ignorees=ecriture.ignorees + resultat.ignorees,
        avec_email=sum(1 for offre in resultat.offres if offre.detail.apply_email),
        pages=resultat.pages_parcourues,
        bloquee=resultat.bloquee,
        casse=casse,
    )

    if resultat.bloquee:
        # Un blocage explique à lui seul l'absence d'offres : une seule alerte.
        log.error("source_bloquee", **asdict(bilan))
        await alerte.envoyer("source_bloquee", source=scraper.source)
    elif casse:
        log.error("scraper_casse", **asdict(bilan))
        await alerte.envoyer(
            "scraper_casse", source=scraper.source, offres_connues=len(ids_connus)
        )
    return bilan


async def ingerer() -> None:
    """Cycle d'ingestion : toutes les sources, l'une après l'autre."""
    settings = get_settings()
    alerte = construire_alerte(settings)

    for classe in SOURCES:
        client = construire_client(classe, settings)
        try:
            async with session_scope() as session:
                bilan = await ingerer_source(classe(client), DepotSql(session), alerte)
            log.info("passe_terminee", **asdict(bilan))
        except Exception as exc:
            # Une source en échec ne doit pas emporter les suivantes ni le worker.
            log.exception("passe_en_echec", source=classe.source)
            await alerte.envoyer("passe_en_echec", source=classe.source, erreur=str(exc))
        finally:
            await client.aclose()


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
