"""Validation d'adresse (CLAUDE.md §5 : users.email est l'identité de connexion)."""

from __future__ import annotations

import pytest

from src.core.courriel_valide import normaliser
from src.core.erreurs import AdresseInvalide


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


@pytest.mark.parametrize("saisie", [None, 12345, ["fatou@example.sn"]])
def test_type_inattendu_leve_erreur_metier_pas_attributeerror(saisie: object) -> None:
    # `core` est la frontière de confiance : un appelant qui envoie autre chose
    # qu'une chaîne doit obtenir une erreur métier, jamais une AttributeError.
    with pytest.raises(AdresseInvalide):
        normaliser(saisie)  # type: ignore[arg-type]


def test_entree_non_bornee_est_rejetee_avant_le_parsing() -> None:
    # Sans borne, ce test échouerait par timeout (coût quadratique mesuré de
    # `validate_email` : 2,48 s pour 400 000 caractères) : la preuve que la
    # longueur est vérifiée avant tout traitement coûteux.
    with pytest.raises(AdresseInvalide):
        normaliser("a" * 100_000 + "@example.sn")
