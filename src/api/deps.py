"""Dépendances FastAPI : session de base, client Redis et compte courant."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated

import redis.asyncio as aioredis
from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import Settings, get_settings
from src.core.auth import cles, jetons
from src.core.erreurs import JetonInvalide
from src.db.models import User
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


async def utilisateur_courant(
    request: Request,
    session: Annotated[AsyncSession, Depends(session_db)],
) -> User:
    """Compte de la session en cours, ou `JetonInvalide` (401).

    `token_version` est comparé à chaque requête : c'est ce qui remplace une
    table de sessions (spec Phase 2 §5). On charge déjà l'utilisateur, donc la
    vérification ne coûte aucune requête supplémentaire.
    """
    settings: Settings = get_settings()
    jeton = request.cookies.get(settings.cookie_session_nom)
    if not jeton:
        raise JetonInvalide(JetonInvalide.code)

    # Clé DÉRIVÉE, jamais le secret brut (tâche 5) : `poser_cookie` signe avec
    # `cles.deriver(secret_brut, "jeton")`, pas `JWT_SECRET` en clair.
    revendications = jetons.decoder(
        jeton, secret=cles.deriver(settings.jwt_secret.get_secret_value(), "jeton")
    )
    resultat = await session.execute(select(User).where(User.id == revendications.user_id))
    utilisateur = resultat.scalar_one_or_none()
    if utilisateur is None or utilisateur.token_version != revendications.token_version:
        raise JetonInvalide(JetonInvalide.code)
    return utilisateur
