"""Les erreurs métier portent un code stable, jamais un texte utilisateur."""

from __future__ import annotations

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


def test_les_erreurs_du_cv_ont_des_codes_stables() -> None:
    """Le client web traduit ces codes en phrases : les renommer casse l'écran."""
    from src.core.erreurs import (
        AnalyseIndisponible,
        CvIllisible,
        CvSansTexte,
        CvTropGros,
        CvTypeRefuse,
        ProfilAbsent,
        TropDAnalyses,
    )

    assert CvTypeRefuse.code == "cv_type_refuse"
    assert CvTropGros.code == "cv_trop_gros"
    assert CvSansTexte.code == "cv_sans_texte"
    assert CvIllisible.code == "cv_illisible"
    assert TropDAnalyses.code == "trop_d_analyses"
    assert AnalyseIndisponible.code == "analyse_indisponible"
    assert ProfilAbsent.code == "profil_absent"
    from src.core.erreurs import CvDocAncien, CvPasUnCv

    assert CvDocAncien.code == "cv_doc_ancien"
    assert CvPasUnCv.code == "cv_pas_un_cv"
