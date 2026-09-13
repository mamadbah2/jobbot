"""Liste des offres (spec du client web §7).

Réservée aux comptes connectés : une liste publique intégrale redistribuerait
gratuitement le fruit du scraping, et viderait de son intérêt le compte que le
modèle économique suppose (décision du 2026-09-13).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, nulls_last, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api import deps
from src.api.schemas.offres import Offre, PageOffres
from src.db.models import Job, User

router = APIRouter(tags=["offres"])


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
    return PageOffres(offres=[Offre.depuis(j) for j in lignes], total=total)
