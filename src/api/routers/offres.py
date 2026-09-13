"""Liste des offres (spec du client web §7).

Réservée aux comptes connectés : une liste publique intégrale redistribuerait
gratuitement le fruit du scraping, et viderait de son intérêt le compte que le
modèle économique suppose (décision du 2026-09-13).
"""

from __future__ import annotations

import asyncio
from typing import Annotated, cast

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, nulls_last, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api import deps
from src.api.schemas.offres import Offre, PageOffres
from src.config import get_settings
from src.db.models import Job, User
from src.ingest.fraicheur import CacheRedis
from src.logging_setup import get_logger
from src.worker_ingest import rafraichir_a_la_demande

log = get_logger(__name__)

router = APIRouter(tags=["offres"])

# `asyncio` ne retient qu'une référence FAIBLE vers une tâche : sans cet
# ensemble, le ramasse-miettes peut emporter la passe en plein vol, au hasard.
_TACHES_DE_FOND: set[asyncio.Task[None]] = set()


async def _rafraichir_en_arriere_plan() -> None:
    """Possède son propre client Redis, et ne le ferme qu'à la toute fin.

    Le client de `deps.cache_redis` est fermé en fin de requête : le passer à
    une tâche de fond laisserait `liberer_verrou` échouer, et la source
    resterait verrouillée pendant `ingest_verrou_secondes` (spec §7).
    """
    client: aioredis.Redis = aioredis.from_url(
        get_settings().redis_url, decode_responses=True
    )
    planifiees: list[asyncio.Task[None]] = []
    try:
        try:
            # `cast` : les stubs de `redis-py` déclarent `delete`/`get`/`set` en
            # retour `T | Awaitable[T]` (client synchrone ET asynchrone confondus),
            # alors que `CacheRedis` déclare des méthodes `async def`. mypy compare
            # alors `Awaitable[T]` à `Coroutine[Any, Any, Any]` et refuse — écart de
            # typage des stubs, pas un vrai défaut de comportement à l'exécution.
            await rafraichir_a_la_demande(
                cast(CacheRedis, client),
                planifier=lambda coro: planifiees.append(asyncio.create_task(coro)),
            )
        finally:
            # Doit s'exécuter même si une source lève en cours de boucle (ou si
            # la tâche est annulée) : sinon des passes déjà planifiées pour des
            # sources précédentes tournent encore quand `client.aclose()`
            # s'exécute plus bas, et `liberer_verrou` échoue sur un client
            # fermé — la source reste verrouillée `ingest_verrou_secondes`
            # (piège n°1 du brief, silencieux).
            if planifiees:
                await asyncio.gather(*planifiees, return_exceptions=True)
    except Exception as exc:  # noqa: BLE001 — une passe ratée ne casse jamais l'affichage
        log.error("rafraichissement_depuis_api_echoue", type_erreur=type(exc).__name__)
    finally:
        await client.aclose()


@router.get("/offres")
async def lister_offres(
    utilisateur: Annotated[User, Depends(deps.utilisateur_courant)],
    session: Annotated[AsyncSession, Depends(deps.session_db)],
    limite: Annotated[int, Query(ge=1, le=50)] = 20,
    decalage: Annotated[int, Query(ge=0)] = 0,
) -> PageOffres:
    """Pagination par décalage : à cette échelle un curseur serait de la
    complexité sans contrepartie, et `ix_jobs_posted_at` existe déjà.

    `nulls_last` n'est pas un détail : `jobs.posted_at` est nullable et Postgres
    place les NULL **en tête** sur un DESC. Sans lui, les offres sans date
    connue occuperaient la première page. Le second critère sur `id` rend
    l'ordre total — sans quoi deux pages successives peuvent répéter ou omettre
    une ligne.
    """
    requete = (
        select(Job)
        .order_by(nulls_last(Job.posted_at.desc()), Job.id.desc())
        .limit(limite)
        .offset(decalage)
    )
    lignes = (await session.execute(requete)).scalars().all()
    total = (await session.execute(select(func.count()).select_from(Job))).scalar_one()

    tache = asyncio.create_task(_rafraichir_en_arriere_plan())
    _TACHES_DE_FOND.add(tache)
    tache.add_done_callback(_TACHES_DE_FOND.discard)

    return PageOffres(offres=[Offre.depuis(j) for j in lignes], total=total)
