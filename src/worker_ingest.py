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
from collections.abc import Callable, Coroutine
from dataclasses import asdict, dataclass
from typing import Any, Final

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
from src.ingest.fraicheur import CacheRedis, Decision, rafraichir_si_necessaire
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
        # Surtout pas de redirection : le saut est décidé par un en-tête du
        # site et échapperait au contrôle de chemin, à robots.txt et au délai
        # de §2.4, tous appliqués avant l'appel.
        httpx.AsyncClient(timeout=TIMEOUT_HTTP, follow_redirects=False),
        user_agent=settings.scraper_user_agent,
        # Le réglage global est un plancher ; une source dont la reconnaissance
        # a validé un rythme plus lent garde le sien (§7).
        delai=max(settings.scraper_delay_seconds, classe.delai_minimum),
        horloge=time.monotonic,
        dormir=asyncio.sleep,
        # Plancher : tient même si le robots.txt du site est injoignable (§7).
        chemins_interdits=classe.chemins_interdits,
        # Les URL d'annonces proviennent d'un href du site : sans périmètre,
        # un lien hostile ferait sortir le scraper du domaine (§2.4).
        hotes_autorises=frozenset({classe.domaine}),
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


async def rafraichir_a_la_demande(
    cache: CacheRedis,
    *,
    planifier: Callable[[Coroutine[Any, Any, None]], Any] = asyncio.create_task,
) -> dict[str, Decision]:
    """Point d'entrée de l'API : appelé quand un utilisateur ouvre la plateforme.

    Ne bloque jamais l'appelant. L'API sert les offres déjà en base, et cette
    fonction déclenche au besoin une passe de fond — au plus une à la fois par
    source, grâce au verrou Redis (§2.4).

    `planifier` est injectable pour que l'appelant sache quand le travail de
    fond est terminé : l'API doit fermer son client Redis **après**, pas avant
    (spec du client web §7).
    """
    settings = get_settings()
    decisions: dict[str, Decision] = {}
    for classe in SOURCES:

        async def passe(classe: type[BaseScraper] = classe) -> None:
            client = construire_client(classe, settings)
            try:
                async with session_scope() as session:
                    await ingerer_source(
                        classe(client), DepotSql(session), construire_alerte(settings)
                    )
            finally:
                await client.aclose()

        decisions[classe.source] = await rafraichir_si_necessaire(
            cache,
            classe.source,
            fraicheur_secondes=settings.ingest_fraicheur_minutes * 60,
            duree_verrou_secondes=settings.ingest_verrou_secondes,
            executer_passe=passe,
            planifier=planifier,
        )
    return decisions
