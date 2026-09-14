"""Rafraîchissement à la demande, déclenché par une visite (CLAUDE.md §2.4, §7).

La fraîcheur se mesure à la **dernière passe réussie**, jamais à la date de la
dernière offre : un dimanche sans publication, ce second critère serait faux
toute la journée et chaque visite relancerait une passe pour rien.

Le verrou est ce qui rend la fonctionnalité compatible avec §2.4. Le limiteur
de débit vit dans un objet en mémoire : dix visites simultanées lanceraient dix
passes qui ne se verraient pas, donc dix requêtes d'un coup sur le même
domaine. Un bannissement d'IP au niveau Cloudflare emporterait TOUTES les
sources, pas seulement celle qu'on rafraîchit.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Coroutine
from dataclasses import dataclass
from typing import Any

from src.core.cache import CacheRedis
from src.logging_setup import get_logger

log = get_logger(__name__)

_PREFIXE = "jobbot:ingest"


@dataclass(frozen=True, slots=True)
class Decision:
    """Faut-il lancer une passe, et pourquoi — la raison part dans les logs."""

    rafraichir: bool
    raison: str


def _cle_passe(source: str) -> str:
    return f"{_PREFIXE}:{source}:derniere_passe"


def _cle_verrou(source: str) -> str:
    return f"{_PREFIXE}:{source}:verrou"


async def demander_rafraichissement(
    cache: CacheRedis, source: str, *, fraicheur_secondes: int, duree_verrou_secondes: int
) -> Decision:
    """Autorise au plus une passe à la fois, et seulement si la dernière date."""
    if await cache.get(_cle_passe(source)) is not None:
        return Decision(False, "passe_recente")

    # SET NX : le premier arrivé obtient le verrou, les autres repartent
    # immédiatement. Le TTL libère la source si une passe meurt en chemin.
    obtenu = await cache.set(
        _cle_verrou(source), "1", ex=duree_verrou_secondes, nx=True
    )
    if not obtenu:
        return Decision(False, "passe_deja_en_cours")
    return Decision(True, "rafraichissement_lance")


async def marquer_passe_reussie(
    cache: CacheRedis, source: str, *, fraicheur_secondes: int
) -> None:
    """Pose le repère de fraîcheur ; son TTL EST la durée de validité."""
    await cache.set(_cle_passe(source), "1", ex=fraicheur_secondes)


async def liberer_verrou(cache: CacheRedis, source: str) -> None:
    """À appeler en `finally` : une passe finie ne doit pas bloquer la suivante."""
    await cache.delete(_cle_verrou(source))


async def _executer_puis_liberer(
    cache: CacheRedis,
    source: str,
    executer_passe: Callable[[], Awaitable[None]],
    fraicheur_secondes: int,
) -> None:
    """Passe de fond : ne marque « frais » qu'en cas de succès."""
    try:
        await executer_passe()
    except Exception as exc:
        # Volontairement PAS de repère de fraîcheur : une passe ratée ne doit
        # pas faire croire à une base à jour pendant 30 minutes.
        log.error("rafraichissement_echoue", source=source, error=str(exc))
        raise
    else:
        await marquer_passe_reussie(cache, source, fraicheur_secondes=fraicheur_secondes)
        log.info("rafraichissement_termine", source=source)
    finally:
        await liberer_verrou(cache, source)


async def rafraichir_si_necessaire(
    cache: CacheRedis,
    source: str,
    *,
    fraicheur_secondes: int,
    duree_verrou_secondes: int,
    executer_passe: Callable[[], Awaitable[None]],
    planifier: Callable[[Coroutine[Any, Any, None]], Any] = asyncio.create_task,
) -> Decision:
    """Décide, planifie en arrière-plan, et rend la main immédiatement.

    L'appelant (l'API, qui sert le web) sert d'abord ce qu'il a en base :
    l'utilisateur est sur une 3G comptée et ne doit jamais attendre une passe
    de scraping (§11).
    """
    decision = await demander_rafraichissement(
        cache,
        source,
        fraicheur_secondes=fraicheur_secondes,
        duree_verrou_secondes=duree_verrou_secondes,
    )
    if decision.rafraichir:
        planifier(
            _executer_puis_liberer(cache, source, executer_passe, fraicheur_secondes)
        )
    log.info("rafraichissement_demande", source=source, raison=decision.raison)
    return decision
