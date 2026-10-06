"""Primitives de comptage à fenêtre fixe sur Redis.

Partagées par les plafonds d'authentification (`core/auth/limites.py`) et par le
plafond d'analyses de CV (`core/cv_limites.py`). Elles vivaient dans le premier,
en privé ; le second en a besoin, et les dupliquer aurait fait deux compteurs à
corriger le jour où l'un se révèle faux.
"""

from __future__ import annotations

from datetime import UTC, datetime

from src.core.auth.cles import empreinte_hex
from src.core.cache import CacheRedis


def empreinte(valeur: str, secret: str) -> str:
    """Clé Redis opaque : ni l'adresse, ni l'IP, ni l'identifiant utilisateur n'y
    figurent en clair (§14.4).

    Tronquée à 32 caractères — une clé Redis n'a pas besoin des 64 du digest
    complet, et la collision reste hors d'atteinte à cette longueur.
    """
    return empreinte_hex(secret, valeur)[:32]


def fenetre_heure() -> str:
    # Fenêtre fixe, pas glissante : une requête à 12:59:59 et une à 13:00:01
    # tombent dans deux fenêtres différentes, ce qui autorise jusqu'au double
    # du débit nominal pendant quelques secondes à la frontière. Assumé — les
    # plafonds journalier et global continuent de borner les dégâts, et une
    # fenêtre glissante coûterait nettement plus cher en complexité pour un
    # gain qui ne change pas la nature du risque (§2.5, pas de sur-ingénierie).
    return datetime.now(UTC).strftime("%Y%m%d%H")


def fenetre_jour() -> str:
    return datetime.now(UTC).strftime("%Y%m%d")


async def incrementer(cache: CacheRedis, cle: str, duree: int) -> int:
    """Compteur à fenêtre fixe : la clé porte la fenêtre, le TTL la nettoie.

    Le TTL est (re)posé à chaque passage avec `NX`, et non seulement à la
    création. Sans cela, un processus qui meurt entre l'`incr` et l'`expire`
    laisse une clé éternelle : une fois le plafond franchi, la cible est
    bloquée pour toujours et il faut intervenir à la main dans Redis.
    `NX` rend l'opération auto-réparante sans jamais rallonger une fenêtre
    déjà en cours.
    """
    valeur = await cache.incr(cle)
    await cache.expire(cle, duree, nx=True)
    return int(valeur)
