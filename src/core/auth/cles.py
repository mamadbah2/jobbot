"""Dérivation d'une clé par usage à partir du secret unique (séparation des clés).

Un seul `JWT_SECRET` est fourni par l'exploitant, mais il alimente quatre usages
cryptographiques distincts : la signature des jetons, le hachage des codes de
vérification, celui des clés de limitation, et celui des jetons de liaison
Telegram. Les employer bruts ferait qu'une faiblesse découverte sur l'un
compromettrait les autres.

HMAC-SHA256 avec une étiquette d'usage comme message est une dérivation à sens
unique suffisante ici : elle est standard (c'est l'étape « expand » de HKDF avec
un seul bloc), elle ne demande aucune dépendance, et retrouver le secret depuis
une clé dérivée revient à casser HMAC.
"""

from __future__ import annotations

import hmac
from hashlib import sha256
from typing import Literal

Usage = Literal["jeton", "code", "limite", "liaison"]


def empreinte_hex(cle: str, message: str) -> str:
    """HMAC-SHA256 en hexadécimal — primitive commune à la dérivation de clés,
    au hachage des codes et à celui des clés de limitation.

    Une seule implémentation : trois copies du même calcul finiraient par
    diverger, et une divergence silencieuse sur un HMAC ne se voit pas en test.
    """
    return hmac.new(cle.encode(), message.encode(), sha256).hexdigest()


def deriver(secret: str, usage: Usage) -> str:
    """Clé dédiée à un usage, en hexadécimal."""
    return empreinte_hex(secret, f"jobbot:cle:{usage}")
