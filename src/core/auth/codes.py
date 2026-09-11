"""Codes de vérification à usage unique (CLAUDE.md §2, interdiction n°2).

Deux propriétés, chacune pour une raison précise :

- **Rien en clair.** L'adresse ET le code sont hachés en HMAC-SHA256 avant
  d'entrer en Redis. Un dump Redis n'expose ni qui s'inscrit, ni avec quel code.
- **Usage unique.** Le code est détruit dès qu'il a servi, sinon il resterait
  valable jusqu'à son TTL et un rejeu suffirait à ouvrir la session.

**La force brute est arrêtée par la CADENCE, pas par la destruction du code**
(`src/core/auth/limites.py` : `auth_verifications_par_heure`, plafond par
adresse consommé uniquement sur un code réellement faux). Avec un TTL de
300 s et 20 tentatives par adresse et par heure, un attaquant dispose d'au
plus 20 essais sur 10^6 possibilités — hors d'atteinte.

Une version antérieure détruisait le code au bout de N échecs. C'était une
vulnérabilité, pas une protection : `/auth/code/verifie` est public, donc
n'importe qui connaissant l'adresse d'une victime pouvait lui envoyer cinq
codes bidon pour détruire le code qu'elle venait de recevoir, puis la
regarder essuyer un `code_expire` en présentant le bon. Et le sondage était
gratuit : une tentative contre une adresse sans code en cours ne crée aucune
clé (elle lève `CodeExpire` avant tout `incr`), donc rien n'empêchait de
sonder en boucle pour savoir quand frapper. **Ne réintroduis pas cette
destruction** : elle ne durcit rien, elle donne à un tiers un moyen de
verrouiller le compte d'autrui pour le prix de cinq requêtes HTTP.
"""

from __future__ import annotations

import hmac
import secrets

from src.core.auth.cles import empreinte_hex
from src.core.cache import CacheRedis
from src.core.erreurs import CodeExpire, CodeInvalide

_PREFIXE = "jobbot:auth"


def generer_code() -> str:
    """Six chiffres tirés cryptographiquement, zéros de tête conservés."""
    return f"{secrets.randbelow(1_000_000):06d}"


def _empreinte(valeur: str, secret: str) -> str:
    return empreinte_hex(secret, valeur)


def _cle_code(adresse: str, secret: str) -> str:
    return f"{_PREFIXE}:code:{_empreinte(adresse, secret)}"


async def deposer(
    cache: CacheRedis, adresse: str, code: str, *, secret: str, ttl_secondes: int
) -> None:
    """Remplace tout code en cours."""
    await cache.set(
        _cle_code(adresse, secret), _empreinte(code, secret), ex=ttl_secondes
    )


async def oublier(cache: CacheRedis, adresse: str, *, secret: str) -> None:
    """Détruit le code."""
    await cache.delete(_cle_code(adresse, secret))


async def verifier(cache: CacheRedis, adresse: str, code: str, *, secret: str) -> None:
    """Ne rend rien en cas de succès ; lève sinon. Le code est consommé."""
    attendu = await cache.get(_cle_code(adresse, secret))
    if attendu is None:
        raise CodeExpire(CodeExpire.code)

    if isinstance(attendu, bytes):
        attendu = attendu.decode()

    # `compare_digest` plutôt que `==` : une comparaison qui s'arrête au premier
    # caractère différent laisse fuiter le préfixe correct par son temps de réponse.
    if hmac.compare_digest(attendu, _empreinte(code, secret)):
        await oublier(cache, adresse, secret=secret)
        return

    raise CodeInvalide(CodeInvalide.code)
