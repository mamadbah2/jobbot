"""Compte courant et liaison Telegram (spec Phase 2 §9)."""

from __future__ import annotations

import secrets
from typing import Annotated

from fastapi import APIRouter, Depends

from src.api import deps
from src.api.schemas.auth import Utilisateur
from src.config import Settings
from src.core.alerte import AlerteAdmin
from src.core.auth import cles
from src.core.cache import CacheRedis
from src.core.erreurs import LiaisonIndisponible
from src.db.models import User

router = APIRouter(tags=["moi"])

# Assez long pour le partager par-dessus l'épaule, assez court pour ne pas
# traîner : le lien ouvre une session Telegram sur le compte. Constante
# d'ergonomie, pas un levier commercial (§6/§8) : elle reste en dur ici
# plutôt que dans `src/config.py` (amendement 3, tâche 14).
LIAISON_TTL_SECONDES = 600
_PREFIXE_LIAISON = "jobbot:auth:liaison"
# Séparé par un tiret, pas par `:`, pour qu'aucun balayage par préfixe sur
# `jobbot:auth:liaison:` ne puisse un jour confondre les jetons eux-mêmes
# avec la clé qui pointe vers le jeton actif d'un compte (round de
# correction 1, tâche 14).
_PREFIXE_LIAISON_ACTIF = "jobbot:auth:liaison-actif"


@router.get("/moi")
async def moi(
    utilisateur: Annotated[User, Depends(deps.utilisateur_courant)],
) -> Utilisateur:
    return Utilisateur.depuis(utilisateur)


@router.post("/moi/telegram/jeton")
async def jeton_de_liaison(
    utilisateur: Annotated[User, Depends(deps.utilisateur_courant)],
    cache: Annotated[CacheRedis, Depends(deps.cache_redis)],
    settings: Annotated[Settings, Depends(deps.reglages)],
    canal_alerte: Annotated[AlerteAdmin, Depends(deps.alerte)],
) -> dict[str, object]:
    """Lien profond de liaison, pour qui utilise Telegram avec un autre numéro.

    Repli du chemin normal, qui est le bouton natif « partager mon contact ».
    Jeton à usage unique : le bot le consomme à la première utilisation.
    Non devinable (`secrets.token_urlsafe`) et jamais journalisé — et jamais
    stocké en clair dans Redis non plus : seule son empreinte HMAC y figure,
    comme `codes.py` le fait pour l'adresse et le code (revue finale,
    corrections mineures). Un dump Redis n'expose donc aucun jeton utilisable.

    Un seul jeton valide à la fois par compte : en redemander un périme le
    précédent, pour ne pas accumuler d'occasions qu'un lien fuite (round de
    correction 1, tâche 14).
    """
    if not settings.telegram_bot_username:
        # Sans nom de bot, le lien produit serait `https://t.me/?start=...` :
        # valide en apparence, inutilisable en pratique, et silencieux. Mieux
        # vaut un refus explicite qu'un lien mort (§7, ne jamais échouer en silence).
        await canal_alerte.envoyer("telegram_bot_username_absent")
        raise LiaisonIndisponible(LiaisonIndisponible.code)

    secret_liaison = cles.deriver(settings.jwt_secret.get_secret_value(), "liaison")

    cle_actif = f"{_PREFIXE_LIAISON_ACTIF}:{utilisateur.id}"
    empreinte_ancienne = await cache.get(cle_actif)
    if empreinte_ancienne is not None:
        if isinstance(empreinte_ancienne, bytes):
            empreinte_ancienne = empreinte_ancienne.decode()
        await cache.delete(f"{_PREFIXE_LIAISON}:{empreinte_ancienne}")

    jeton = secrets.token_urlsafe(24)
    empreinte = cles.empreinte_hex(secret_liaison, jeton)
    # Le pointeur AVANT le jeton : un arrêt entre les deux écritures laisse
    # alors un pointeur vers un jeton inexistant — inoffensif, et rattrapé par
    # l'appel suivant. L'ordre inverse laisserait un jeton valide qu'aucun
    # pointeur ne désigne, donc qu'aucune émission ultérieure ne périmerait
    # (round de correction 2, tâche 14). Seule l'EMPREINTE circule entre les
    # deux clés : le jeton en clair ne quitte cette fonction que dans le lien
    # renvoyé à l'appelant, jamais vers Redis.
    await cache.set(cle_actif, empreinte, ex=LIAISON_TTL_SECONDES)
    await cache.set(
        f"{_PREFIXE_LIAISON}:{empreinte}", str(utilisateur.id), ex=LIAISON_TTL_SECONDES
    )
    return {
        "lien": f"https://t.me/{settings.telegram_bot_username}?start={jeton}",
        "expire_dans": LIAISON_TTL_SECONDES,
    }
