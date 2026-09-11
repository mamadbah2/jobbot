"""Jetons de session (spec Phase 2 §5 : pas de table de sessions)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import jwt
import pytest

from src.core.auth.jetons import Revendications, decoder, encoder
from src.core.erreurs import JetonInvalide

SECRET = "secret_de_test"


def test_aller_retour() -> None:
    jeton = encoder(user_id=7, token_version=3, secret=SECRET, duree_jours=30)
    assert decoder(jeton, secret=SECRET) == Revendications(user_id=7, token_version=3)


def test_signature_d_un_autre_secret_refusee() -> None:
    jeton = encoder(user_id=7, token_version=0, secret="autre_secret", duree_jours=30)
    with pytest.raises(JetonInvalide):
        decoder(jeton, secret=SECRET)


def test_jeton_altere_refuse() -> None:
    jeton = encoder(user_id=7, token_version=0, secret=SECRET, duree_jours=30)
    altere = jeton[:-4] + ("aaaa" if not jeton.endswith("aaaa") else "bbbb")
    with pytest.raises(JetonInvalide):
        decoder(altere, secret=SECRET)


def test_jeton_expire_refuse() -> None:
    passe = datetime.now(UTC) - timedelta(days=1)
    jeton = jwt.encode(
        {"sub": "7", "tv": 0, "exp": passe, "iat": passe}, SECRET, algorithm="HS256"
    )
    with pytest.raises(JetonInvalide):
        decoder(jeton, secret=SECRET)


def test_chaine_quelconque_refusee() -> None:
    with pytest.raises(JetonInvalide):
        decoder("pas-un-jeton", secret=SECRET)


def test_algorithme_none_refuse() -> None:
    """Attaque classique : un jeton signé `alg: none` ne doit jamais être accepté."""
    jeton = jwt.encode({"sub": "7", "tv": 0}, key="", algorithm="none")
    with pytest.raises(JetonInvalide):
        decoder(jeton, secret=SECRET)


def test_revendications_manquantes_refusees() -> None:
    futur = datetime.now(UTC) + timedelta(days=1)
    jeton = jwt.encode({"exp": futur}, SECRET, algorithm="HS256")
    with pytest.raises(JetonInvalide):
        decoder(jeton, secret=SECRET)
