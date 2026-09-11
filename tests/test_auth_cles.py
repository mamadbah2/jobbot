"""Dérivation d'une clé par usage (séparation des clés, amendement à la tâche 5)."""

from __future__ import annotations

from src.core.auth import cles

SECRET = "secret_de_test"


def test_les_trois_usages_donnent_des_cles_differentes() -> None:
    jeton = cles.deriver(SECRET, "jeton")
    code = cles.deriver(SECRET, "code")
    limite = cles.deriver(SECRET, "limite")
    assert len({jeton, code, limite}) == 3


def test_la_derivation_est_deterministe() -> None:
    assert cles.deriver(SECRET, "code") == cles.deriver(SECRET, "code")


def test_deux_secrets_differents_donnent_des_cles_differentes() -> None:
    assert cles.deriver(SECRET, "code") != cles.deriver("autre_secret", "code")


def test_la_cle_derivee_ne_contient_jamais_le_secret() -> None:
    assert SECRET not in cles.deriver(SECRET, "jeton")
    assert SECRET not in cles.deriver(SECRET, "code")
    assert SECRET not in cles.deriver(SECRET, "limite")
