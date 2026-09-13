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


def test_empreinte_hex_est_deterministe() -> None:
    assert cles.empreinte_hex("cle", "message") == cles.empreinte_hex("cle", "message")


def test_empreinte_hex_varie_avec_la_cle() -> None:
    assert cles.empreinte_hex("cle_a", "message") != cles.empreinte_hex("cle_b", "message")


def test_empreinte_hex_varie_avec_le_message() -> None:
    assert cles.empreinte_hex("cle", "message_a") != cles.empreinte_hex("cle", "message_b")


def test_empreinte_hex_ne_contient_ni_la_cle_ni_le_message() -> None:
    resultat = cles.empreinte_hex("cle_secrete", "message_en_clair")
    assert "cle_secrete" not in resultat
    assert "message_en_clair" not in resultat
