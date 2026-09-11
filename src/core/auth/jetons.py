"""Jetons de session (spec Phase 2 §5).

Pas de table de sessions, pas de jeton de rafraîchissement : un seul jeton
d'accès de 30 jours portant `token_version`. On charge déjà l'utilisateur à
chaque requête authentifiée, donc comparer la version ne coûte rien de plus.
Se déconnecter de partout = incrémenter la colonne.

Prix assumé : un jeton volé reste valable jusqu'à révocation explicite.

Le paramètre `secret` de `encoder`/`decoder` n'est jamais le `JWT_SECRET` brut
de la configuration : c'est la clé dédiée à la signature des jetons, dérivée
par `src.core.auth.cles.deriver` (séparation des clés décidée en tâche 5 — un
même secret d'exploitation alimente plusieurs usages cryptographiques
distincts, chacun avec sa propre clé dérivée).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import jwt

from src.core.erreurs import JetonInvalide

ALGORITHME = "HS256"


@dataclass(frozen=True, slots=True)
class Revendications:
    """Ce qu'un jeton valide affirme."""

    user_id: int
    token_version: int


def encoder(*, user_id: int, token_version: int, secret: str, duree_jours: int) -> str:
    """Signe un jeton de session avec la clé dédiée aux jetons."""
    emission = datetime.now(UTC)
    charge = {
        "sub": str(user_id),
        "tv": token_version,
        "iat": emission,
        "exp": emission + timedelta(days=duree_jours),
    }
    return jwt.encode(charge, secret, algorithm=ALGORITHME)


def decoder(jeton: str, *, secret: str) -> Revendications:
    """Vérifie signature et expiration, ou lève `JetonInvalide`.

    `algorithms` est explicitement restreint : sans cette liste, un jeton forgé
    avec `alg: none` serait accepté sans aucune signature. `token_version` est
    rendue telle quelle : c'est à l'appelant (tâche 14) de la comparer à celle
    du compte pour détecter un jeton révoqué.
    """
    try:
        charge = jwt.decode(jeton, secret, algorithms=[ALGORITHME])
        return Revendications(user_id=int(charge["sub"]), token_version=int(charge["tv"]))
    except (jwt.PyJWTError, KeyError, TypeError, ValueError) as exc:
        raise JetonInvalide(JetonInvalide.code) from exc
