"""Validation d'adresse (CLAUDE.md §5 : users.email est l'identité de connexion)."""

from __future__ import annotations

import pytest

from src.core.courriel_valide import normaliser


def test_adresse_simple() -> None:
    assert normaliser("fatou@example.sn") == "fatou@example.sn"


def test_casse_et_espaces_normalises() -> None:
    assert normaliser("  Fatou.Diop@Example.SN  ") == "Fatou.Diop@example.sn"


def test_deux_ecritures_du_meme_domaine_convergent() -> None:
    # L'unicité de users.email ne protège rien si le domaine n'est pas normalisé.
    assert normaliser("a@EXAMPLE.sn") == normaliser("a@example.SN")


@pytest.mark.parametrize(
    "saisie",
    ["", "   ", "fatou", "fatou@", "@example.sn", "fatou@@example.sn", "fatou example@a.sn"],
)
def test_adresses_refusees(saisie: str) -> None:
    with pytest.raises(ValueError):
        normaliser(saisie)
