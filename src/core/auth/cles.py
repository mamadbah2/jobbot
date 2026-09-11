"""Dérivation d'une clé par usage à partir du secret unique (séparation des clés).

Un seul `JWT_SECRET` est fourni par l'exploitant, mais il alimente trois usages
cryptographiques distincts : la signature des jetons, le hachage des codes de
vérification et celui des clés de limitation. Les employer bruts ferait qu'une
faiblesse découverte sur l'un compromettrait les deux autres.

HMAC-SHA256 avec une étiquette d'usage comme message est une dérivation à sens
unique suffisante ici : elle est standard (c'est l'étape « expand » de HKDF avec
un seul bloc), elle ne demande aucune dépendance, et retrouver le secret depuis
une clé dérivée revient à casser HMAC.
"""

from __future__ import annotations

import hmac
from hashlib import sha256
from typing import Literal

Usage = Literal["jeton", "code", "limite"]


def deriver(secret: str, usage: Usage) -> str:
    """Clé dédiée à un usage, en hexadécimal."""
    return hmac.new(secret.encode(), f"jobbot:cle:{usage}".encode(), sha256).hexdigest()
