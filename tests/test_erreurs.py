"""Les erreurs métier portent un code stable, jamais un texte utilisateur."""

from __future__ import annotations

import pytest

from src.core import erreurs


def test_toutes_les_erreurs_derivent_d_erreur_metier() -> None:
    for nom in erreurs.__all__:
        classe = getattr(erreurs, nom)
        if classe is erreurs.ErreurMetier:
            continue
        assert issubclass(classe, erreurs.ErreurMetier), nom


def test_chaque_erreur_porte_un_code_non_vide() -> None:
    for nom in erreurs.__all__:
        classe = getattr(erreurs, nom)
        if classe is erreurs.ErreurMetier:
            continue
        assert isinstance(classe.code, str) and classe.code, nom


def test_les_codes_sont_uniques() -> None:
    codes = [
        getattr(erreurs, nom).code
        for nom in erreurs.__all__
        if getattr(erreurs, nom) is not erreurs.ErreurMetier
    ]
    assert len(codes) == len(set(codes))


def test_trop_de_demandes_porte_le_delai() -> None:
    exc = erreurs.TropDeDemandes(attendre_secondes=42)
    assert exc.attendre_secondes == 42
    assert exc.code == "trop_de_demandes"


def test_numero_invalide_est_bien_une_value_error() -> None:
    # Les appelants écrits avant cette tâche attrapent ValueError : ne pas les casser.
    assert issubclass(erreurs.NumeroInvalide, ValueError)
    with pytest.raises(ValueError):
        raise erreurs.NumeroInvalide("numero_hors_senegal")
