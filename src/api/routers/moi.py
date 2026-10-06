"""Compte courant (spec Phase 2 §9).

L'endpoint de liaison Telegram (`POST /moi/telegram/jeton`) a été retiré le
2026-09-12 avec le client Telegram, ainsi que sa mécanique de jeton à usage
unique en Redis : plus de bot à relier, plus de lien profond à produire.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from src.api import deps
from src.api.routers.auth import effacer_cookie
from src.api.routers.profil import cle_image_cv
from src.api.schemas.auth import Utilisateur
from src.config import Settings
from src.core.cache import CacheRedis
from src.db.models import User
from src.logging_setup import get_logger

log = get_logger(__name__)

router = APIRouter(tags=["moi"])


@router.get("/moi")
async def moi(
    utilisateur: Annotated[User, Depends(deps.utilisateur_courant)],
) -> Utilisateur:
    return Utilisateur.depuis(utilisateur)


@router.delete("/moi", status_code=status.HTTP_204_NO_CONTENT)
async def supprimer_mes_donnees(
    response: Response,
    utilisateur: Annotated[User, Depends(deps.utilisateur_courant)],
    session: Annotated[AsyncSession, Depends(deps.session_db)],
    settings: Annotated[Settings, Depends(deps.reglages)],
    cache: Annotated[CacheRedis, Depends(deps.cache_redis)],
) -> None:
    """Supprime le compte et tout ce qui en dépend (§14.4).

    `profiles`, `applications`, `subscriptions` et `usage_counters` portent
    `ondelete="CASCADE"` sur `user_id` : supprimer la ligne `users` emporte le
    CV et le profil structuré. Immédiat, sans corbeille — c'est ce que
    « supprimer mes données » veut dire.

    Le cookie est effacé dans la même réponse : laisser un jeton valide pointer
    vers un compte disparu enverrait l'utilisateur sur un 401 inexpliqué au
    prochain écran plutôt que sur la page de connexion.
    """
    user_id = utilisateur.id
    # Un `DELETE` SQL et non `session.delete(utilisateur)` : l'ORM, qui connaît
    # `User.profile` sans cascade, mettrait `profiles.user_id` à NULL avant de
    # supprimer l'utilisateur, et la base refuserait (NOT NULL). Constaté : la
    # route répondait 204, le commit échouait APRÈS la réponse, et le compte
    # restait. Ici c'est la base qui cascade, comme la migration le déclare.
    await session.execute(delete(User).where(User.id == user_id))
    # Valider avant de répondre : un 204 doit vouloir dire « c'est effacé », pas
    # « le commit de fin de requête essaiera ». Sans cela, un échec de commit
    # surviendrait une fois la réponse partie, invisible du client.
    await session.commit()
    # L'image brute d'un CV en attente d'analyse : la donnée la plus sensible du
    # produit. Clé déterministe, donc un `DELETE` en O(1) (pas de `SCAN`).
    await cache.delete(cle_image_cv(user_id))
    effacer_cookie(response, settings)
    # L'identifiant seulement : l'adresse est une donnée personnelle, et on
    # vient précisément de promettre de l'effacer.
    log.info("compte_supprime", user_id=user_id)
