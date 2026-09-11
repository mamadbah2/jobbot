"""Normalisation des numéros (CLAUDE.md §5 : users.phone est unique et obligatoire)."""

from __future__ import annotations

import pytest

from src.core.telephone import normaliser

ATTENDU = "+221771234567"


@pytest.mark.parametrize(
    "saisie",
    [
        "+221771234567",
        "+221 77 123 45 67",
        "00221771234567",
        "221771234567",
        "771234567",
        "77 123 45 67",
        "  77-123-45-67  ",
    ],
)
def test_formats_locaux_acceptes(saisie: str) -> None:
    assert normaliser(saisie) == ATTENDU


@pytest.mark.parametrize(
    "saisie",
    [
        "",
        "   ",
        "bonjour",
        "12345",
        "7712345",            # trop court
        "+33612345678",       # numéro français : hors Sénégal
        "+1 415 555 0132",    # numéro américain
    ],
)
def test_numeros_refuses(saisie: str) -> None:
    with pytest.raises(ValueError):
        normaliser(saisie)


def test_numero_fixe_senegalais_accepte() -> None:
    assert normaliser("338591010") == "+221338591010"
