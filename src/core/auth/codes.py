"""Codes de vérification à usage unique (CLAUDE.md §2, interdiction n°2).

Trois propriétés, chacune pour une raison précise :

- **Rien en clair.** L'adresse ET le code sont hachés en HMAC-SHA256 avant
  d'entrer en Redis. Un dump Redis n'expose ni qui s'inscrit, ni avec quel code.
- **Usage unique.** Le code est détruit dès qu'il a servi, sinon il resterait
  valable jusqu'à son TTL et un rejeu suffirait à ouvrir la session.
- **Nombre d'essais borné.** Sans cela, 10^6 essais suffisent à deviner six
  chiffres. Au-delà du plafond, le code est DÉTRUIT, pas simplement refusé :
  refuser laisserait l'attaquant redemander un envoi et reprendre son décompte.
"""

from __future__ import annotations

import hmac
import secrets
from hashlib import sha256

from src.core.cache import CacheRedis
from src.core.erreurs import CodeExpire, CodeInvalide

_PREFIXE = "jobbot:auth"


def generer_code() -> str:
    """Six chiffres tirés cryptographiquement, zéros de tête conservés."""
    return f"{secrets.randbelow(1_000_000):06d}"


def _empreinte(valeur: str, secret: str) -> str:
    return hmac.new(secret.encode(), valeur.encode(), sha256).hexdigest()


def _cle_code(adresse: str, secret: str) -> str:
    return f"{_PREFIXE}:code:{_empreinte(adresse, secret)}"


def _cle_essais(adresse: str, secret: str) -> str:
    return f"{_PREFIXE}:essais:{_empreinte(adresse, secret)}"


async def deposer(
    cache: CacheRedis, adresse: str, code: str, *, secret: str, ttl_secondes: int
) -> None:
    """Remplace tout code en cours et remet le compteur d'essais à zéro."""
    await cache.delete(_cle_essais(adresse, secret))
    await cache.set(
        _cle_code(adresse, secret), _empreinte(code, secret), ex=ttl_secondes
    )


async def oublier(cache: CacheRedis, adresse: str, *, secret: str) -> None:
    """Détruit le code et son compteur."""
    await cache.delete(_cle_code(adresse, secret), _cle_essais(adresse, secret))


async def verifier(
    cache: CacheRedis, adresse: str, code: str, *, secret: str, essais_max: int
) -> None:
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

    essais = await cache.incr(_cle_essais(adresse, secret))
    if essais == 1:
        # Le compteur ne doit pas survivre au code lui-même.
        await cache.expire(_cle_essais(adresse, secret), 3600)
    if essais >= essais_max:
        await oublier(cache, adresse, secret=secret)

    raise CodeInvalide(CodeInvalide.code)
