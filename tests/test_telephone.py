"""Normalisation des numéros (CLAUDE.md §5 : users.phone est unique et obligatoire)."""

from __future__ import annotations

import pytest

from src.core.erreurs import NumeroInvalide
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


@pytest.mark.parametrize("saisie", [None, 12345, ["77", "12", "34", "56"]])
def test_type_inattendu_leve_erreur_metier_pas_attributeerror(saisie: object) -> None:
    # `core` est la frontière de confiance : un appelant qui envoie autre chose
    # qu'une chaîne doit obtenir une erreur métier, jamais une AttributeError.
    with pytest.raises(NumeroInvalide):
        normaliser(saisie)  # type: ignore[arg-type]


def test_entree_non_bornee_est_rejetee_avant_le_parsing() -> None:
    # Sans borne, ce test échouerait par timeout : la preuve que la longueur
    # est vérifiée avant tout traitement coûteux.
    with pytest.raises(NumeroInvalide):
        normaliser("7" * 100_000)
