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

from src.core.alerte import AlerteAdmin
from src.core.cache import CacheRedis
from src.core.erreurs import PlafondGlobalAtteint, TropDeDemandes
from src.core.limites import empreinte, fenetre_heure, fenetre_jour, incrementer

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
    empreinte_adresse = empreinte(adresse, secret)

    if regles.cooldown_secondes > 0:
        pose = await cache.set(
            f"{_PREFIXE}:cooldown:{empreinte_adresse}", "1", ex=regles.cooldown_secondes, nx=True
        )
        if not pose:
            raise TropDeDemandes(attendre_secondes=regles.cooldown_secondes)

    heure = await incrementer(cache, f"{_PREFIXE}:h:{empreinte_adresse}:{fenetre_heure()}", _HEURE)
    if heure > regles.par_heure:
        raise TropDeDemandes(attendre_secondes=_HEURE)

    jour = await incrementer(cache, f"{_PREFIXE}:j:{empreinte_adresse}:{fenetre_jour()}", _JOUR)
    if jour > regles.par_jour:
        raise TropDeDemandes(attendre_secondes=_JOUR)

    ip_heure = await incrementer(
        cache, f"{_PREFIXE}:ip:{empreinte(ip, secret)}:{fenetre_heure()}", _HEURE
    )
    if ip_heure > regles.par_ip_heure:
        raise TropDeDemandes(attendre_secondes=_HEURE)

    total = await incrementer(cache, f"{_PREFIXE}:global:{fenetre_jour()}", _JOUR)
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
    cache: CacheRedis, *, ip: str, regles: ReglesVerification, secret: str
) -> None:
    """Borne la CADENCE des tentatives venant d'une même origine réseau.

    Volontairement indexé sur la seule IP, et non sur l'adresse : un compteur
    par adresse consommé avant toute preuve de possession permettrait à
    n'importe qui connaissant l'email d'une victime de bloquer ses connexions
    en envoyant des codes bidon. Le plafond par adresse existe aussi, mais il
    ne se consomme que sur un code réellement faux (`compter_code_invalide`).
    """
    ip_heure = await incrementer(
        cache, f"{_PREFIXE}:vip:{empreinte(ip, secret)}:{fenetre_heure()}", _HEURE
    )
    if ip_heure > regles.par_ip_heure:
        raise TropDeDemandes(attendre_secondes=_HEURE)


async def compter_code_invalide(
    cache: CacheRedis, *, adresse: str, regles: ReglesVerification, secret: str
) -> None:
    """Compte un échec sur un code qui existait vraiment, et plafonne.

    N'est appelé qu'après un `CodeInvalide` : une tentative contre une adresse
    sans code en cours ne consomme donc rien, ce qui ôte tout intérêt à
    marteler l'adresse d'autrui.
    """
    heure = await incrementer(
        cache, f"{_PREFIXE}:vh:{empreinte(adresse, secret)}:{fenetre_heure()}", _HEURE
    )
    if heure > regles.par_heure:
        raise TropDeDemandes(attendre_secondes=_HEURE)
