"""Compte courant (spec Phase 2 §9).

L'endpoint de liaison Telegram (`POST /moi/telegram/jeton`) a été retiré le
2026-09-12 avec le client Telegram, ainsi que sa mécanique de jeton à usage
unique en Redis : plus de bot à relier, plus de lien profond à produire.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from src.api import deps
from src.api.schemas.auth import Utilisateur
from src.db.models import User

router = APIRouter(tags=["moi"])


@router.get("/moi")
async def moi(
    utilisateur: Annotated[User, Depends(deps.utilisateur_courant)],
) -> Utilisateur:
    return Utilisateur.depuis(utilisateur)
