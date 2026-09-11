"""Garde-fous de l'envoi du code (spec Phase 2 §10).

`/auth/code/demande` est public et déclenche un email. Sans limite, il permet
d'inonder la boîte d'un tiers et de brûler la réputation du domaine d'envoi —
la ressource la plus lente à reconstruire du projet.

L'ordre des contrôles est délibéré : les limites de l'appelant d'abord, le
plafond global en dernier. Un attaquant arrêté par sa propre limite ne doit pas
avoir entamé le plafond qui protège tous les autres utilisateurs.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from src.alerting import AlerteAdmin
from src.core.auth.cles import empreinte_hex
from src.core.cache import CacheRedis
from src.core.erreurs import PlafondGlobalAtteint, TropDeDemandes
from src.logging_setup import get_logger

log = get_logger(__name__)

_PREFIXE = "jobbot:auth:limite"
_HEURE = 3600
_JOUR = 86400


@dataclass(frozen=True, slots=True)
class ReglesEnvoi:
    """Plafonds applicables à une demande d'envoi. Tous configurables (§3)."""

    cooldown_secondes: int
    par_heure: int
    par_jour: int
    par_ip_heure: int
    plafond_global_jour: int


def _empreinte(valeur: str, secret: str) -> str:
    """Clé Redis opaque : ni l'adresse ni l'IP n'y figurent en clair (§14.4).

    Tronquée à 32 caractères — une clé Redis n'a pas besoin des 64 du digest
    complet, et la collision reste hors d'atteinte à cette longueur.
    """
    return empreinte_hex(secret, valeur)[:32]


def _fenetre_heure() -> str:
    return datetime.now(UTC).strftime("%Y%m%d%H")


def _fenetre_jour() -> str:
    return datetime.now(UTC).strftime("%Y%m%d")


async def _incrementer(cache: CacheRedis, cle: str, duree: int) -> int:
    """Compteur à fenêtre fixe : la clé porte la fenêtre, le TTL la nettoie."""
    valeur = await cache.incr(cle)
    if valeur == 1:
        await cache.expire(cle, duree)
    return int(valeur)


async def autoriser_envoi(
    cache: CacheRedis,
    *,
    adresse: str,
    ip: str,
    regles: ReglesEnvoi,
    secret: str,
    alerte: AlerteAdmin,
) -> None:
    """Ne rend rien si l'envoi est permis ; lève sinon. Consomme les compteurs."""
    empreinte = _empreinte(adresse, secret)

    if regles.cooldown_secondes > 0:
        pose = await cache.set(
            f"{_PREFIXE}:cooldown:{empreinte}", "1", ex=regles.cooldown_secondes, nx=True
        )
        if not pose:
            raise TropDeDemandes(attendre_secondes=regles.cooldown_secondes)

    heure = await _incrementer(cache, f"{_PREFIXE}:h:{empreinte}:{_fenetre_heure()}", _HEURE)
    if heure > regles.par_heure:
        raise TropDeDemandes(attendre_secondes=_HEURE)

    jour = await _incrementer(cache, f"{_PREFIXE}:j:{empreinte}:{_fenetre_jour()}", _JOUR)
    if jour > regles.par_jour:
        raise TropDeDemandes(attendre_secondes=_JOUR)

    ip_heure = await _incrementer(
        cache, f"{_PREFIXE}:ip:{_empreinte(ip, secret)}:{_fenetre_heure()}", _HEURE
    )
    if ip_heure > regles.par_ip_heure:
        raise TropDeDemandes(attendre_secondes=_HEURE)

    total = await _incrementer(cache, f"{_PREFIXE}:global:{_fenetre_jour()}", _JOUR)
    if total > regles.plafond_global_jour:
        # Ne jamais échouer en silence (§7) : ce plafond signale soit un abus,
        # soit un succès inattendu. Les deux méritent un réveil.
        await alerte.envoyer(
            "plafond_global_envois_atteint",
            plafond=regles.plafond_global_jour,
            compte=total,
        )
        raise PlafondGlobalAtteint(PlafondGlobalAtteint.code)
