"""Dédoublonnage des offres (CLAUDE.md §5).

L'empreinte rapproche une même annonce republiée sur plusieurs portails :
elle ignore la casse, les accents, la ponctuation et les espaces multiples.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata

_NON_ALPHANUM = re.compile(r"[^a-z0-9]+")


def _canonise(valeur: str | None) -> str:
    """Réduit un champ à sa forme comparable : minuscules, sans accent."""
    if not valeur:
        return ""
    sans_accent = unicodedata.normalize("NFKD", valeur)
    sans_accent = "".join(c for c in sans_accent if not unicodedata.combining(c))
    return _NON_ALPHANUM.sub(" ", sans_accent.lower()).strip()


def compute_fingerprint(title: str, company: str | None, location: str | None) -> str:
    """Empreinte hexadécimale d'une offre — tient dans `jobs.fingerprint` (§5)."""
    graine = "|".join(_canonise(champ) for champ in (title, company, location))
    return hashlib.sha256(graine.encode("utf-8")).hexdigest()
