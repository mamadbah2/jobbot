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
    # Fenêtre fixe, pas glissante : une requête à 12:59:59 et une à 13:00:01
    # tombent dans deux fenêtres différentes, ce qui autorise jusqu'au double
    # du débit nominal pendant quelques secondes à la frontière. Assumé — les
    # plafonds journalier et global continuent de borner les dégâts, et une
    # fenêtre glissante coûterait nettement plus cher en complexité pour un
    # gain qui ne change pas la nature du risque (§2.5, pas de sur-ingénierie).
    return datetime.now(UTC).strftime("%Y%m%d%H")


def _fenetre_jour() -> str:
    return datetime.now(UTC).strftime("%Y%m%d")


async def _incrementer(cache: CacheRedis, cle: str, duree: int) -> int:
    """Compteur à fenêtre fixe : la clé porte la fenêtre, le TTL la nettoie.

    Le TTL est (re)posé à chaque passage avec `NX`, et non seulement à la
    création. Sans cela, un processus qui meurt entre l'`incr` et l'`expire`
    laisse une clé éternelle : une fois le plafond franchi, l'adresse est
    bloquée pour toujours et il faut intervenir à la main dans Redis.
    `NX` rend l'opération auto-réparante sans jamais rallonger une fenêtre
    déjà en cours.
    """
    valeur = await cache.incr(cle)
    await cache.expire(cle, duree, nx=True)
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


@dataclass(frozen=True, slots=True)
class ReglesVerification:
    """Plafonds de la vérification de code. Pas de cooldown : un utilisateur
    légitime qui se trompe de chiffre doit pouvoir recommencer tout de suite."""

    par_heure: int
    par_ip_heure: int


async def autoriser_verification(
    cache: CacheRedis, *, adresse: str, ip: str, regles: ReglesVerification, secret: str
) -> None:
    """Ne rend rien si la tentative est permise ; lève `TropDeDemandes` sinon.

    Le compteur d'essais de `codes.verifier` détruit le code au bout de cinq
    échecs, mais il ne borne pas la CADENCE : en parallèle, un attaquant peut
    glisser des tentatives dans la fenêtre entre l'incrément du compteur et la
    destruction du code. Ce plafond borne le nombre total de tentatives, donc
    le nombre de coups portés sur un espace de six chiffres.
    """
    empreinte = _empreinte(adresse, secret)
    heure = await _incrementer(cache, f"{_PREFIXE}:vh:{empreinte}:{_fenetre_heure()}", _HEURE)
    if heure > regles.par_heure:
        raise TropDeDemandes(attendre_secondes=_HEURE)
    ip_heure = await _incrementer(
        cache, f"{_PREFIXE}:vip:{_empreinte(ip, secret)}:{_fenetre_heure()}", _HEURE
    )
    if ip_heure > regles.par_ip_heure:
        raise TropDeDemandes(attendre_secondes=_HEURE)
