"""Compte courant et liaison Telegram (spec Phase 2 §9)."""

from __future__ import annotations

import secrets
from typing import Annotated

from fastapi import APIRouter, Depends

from src.api import deps
from src.api.schemas.auth import Utilisateur
from src.config import Settings, get_settings
from src.core.cache import CacheRedis
from src.db.models import User

router = APIRouter(tags=["moi"])

# Assez long pour le partager par-dessus l'épaule, assez court pour ne pas
# traîner : le lien ouvre une session Telegram sur le compte. Constante
# d'ergonomie, pas un levier commercial (§6/§8) : elle reste en dur ici
# plutôt que dans `src/config.py` (amendement 3, tâche 14).
LIAISON_TTL_SECONDES = 600
_PREFIXE_LIAISON = "jobbot:auth:liaison"


def reglages() -> Settings:
    return get_settings()


@router.get("/moi")
async def moi(
    utilisateur: Annotated[User, Depends(deps.utilisateur_courant)],
) -> Utilisateur:
    return Utilisateur.depuis(utilisateur)


@router.post("/moi/telegram/jeton")
async def jeton_de_liaison(
    utilisateur: Annotated[User, Depends(deps.utilisateur_courant)],
    cache: Annotated[CacheRedis, Depends(deps.cache_redis)],
    settings: Annotated[Settings, Depends(reglages)],
) -> dict[str, object]:
    """Lien profond de liaison, pour qui utilise Telegram avec un autre numéro.

    Repli du chemin normal, qui est le bouton natif « partager mon contact ».
    Jeton à usage unique : le bot le consomme à la première utilisation.
    Non devinable (`secrets.token_urlsafe`) et jamais journalisé.
    """
    jeton = secrets.token_urlsafe(24)
    await cache.set(f"{_PREFIXE_LIAISON}:{jeton}", str(utilisateur.id), ex=LIAISON_TTL_SECONDES)
    return {
        "lien": f"https://t.me/{settings.telegram_bot_username}?start={jeton}",
        "expire_dans": LIAISON_TTL_SECONDES,
    }
