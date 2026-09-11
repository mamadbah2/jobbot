"""Contrôles communs à toute saisie utilisateur (CLAUDE.md : `core` = frontière de confiance)."""

from __future__ import annotations

import pytest

from src.core.erreurs import AdresseInvalide, ErreurMetier
from src.core.saisie import texte_saisi


def test_type_valide_est_nettoye_et_retourne() -> None:
    assert (
        texte_saisi("  bonjour  ", longueur_max=64, erreur=AdresseInvalide, sujet="x")
        == "bonjour"
    )


@pytest.mark.parametrize("valeur", [None, 12345, ["a", "b"], 3.14, {"a": 1}, object()])
def test_type_invalide_leve_erreur_metier(valeur: object) -> None:
    with pytest.raises(ErreurMetier) as exc_info:
        texte_saisi(valeur, longueur_max=64, erreur=AdresseInvalide, sujet="x")
    assert exc_info.value.code == "adresse_invalide"
    assert str(exc_info.value) == "x_invalide"


def test_trop_long_leve_erreur_metier() -> None:
    with pytest.raises(ErreurMetier) as exc_info:
        texte_saisi("a" * 65, longueur_max=64, erreur=AdresseInvalide, sujet="x")
    assert str(exc_info.value) == "x_trop_long"


def test_vide_apres_nettoyage_leve_erreur_metier() -> None:
    with pytest.raises(ErreurMetier) as exc_info:
        texte_saisi("    ", longueur_max=64, erreur=AdresseInvalide, sujet="x")
    assert str(exc_info.value) == "x_vide"


def test_longueur_max_atteinte_pile_est_acceptee() -> None:
    assert texte_saisi("a" * 64, longueur_max=64, erreur=AdresseInvalide, sujet="x") == "a" * 64
