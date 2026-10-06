"""Règle de péremption d'une analyse (spec §6)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from src.core.cv_etat import ANALYSE_INTERROMPUE, etat_affiche

MAINTENANT = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)


def _affiche(
    etat: str, age_secondes: int | None, erreur: str | None = None
) -> tuple[str, str | None]:
    demarre = None if age_secondes is None else MAINTENANT - timedelta(seconds=age_secondes)
    return etat_affiche(etat, demarre, erreur, maintenant=MAINTENANT, delai_max_secondes=300)


def test_une_analyse_recente_reste_en_cours() -> None:
    assert _affiche("en_cours", 10) == ("en_cours", None)


def test_la_borne_exacte_reste_en_cours() -> None:
    """Pile au délai max : pas encore périmée (`>` et non `>=`)."""
    assert _affiche("en_cours", 300) == ("en_cours", None)


def test_une_analyse_trop_vieille_devient_un_echec() -> None:
    """Le cas réel : `api` a redémarré, personne ne reprendra le travail."""
    assert _affiche("en_cours", 301) == ("echec", ANALYSE_INTERROMPUE)


def test_en_cours_sans_date_de_depart_est_suspect() -> None:
    assert _affiche("en_cours", None) == ("echec", ANALYSE_INTERROMPUE)


def test_les_autres_etats_passent_meme_avec_une_date_ancienne() -> None:
    for etat in ("en_attente", "pret", "echec"):
        for age in (None, 10, 100_000):
            assert _affiche(etat, age) == (etat, None)


def test_un_echec_reel_garde_son_code_stocke() -> None:
    assert _affiche("echec", 100_000, "cv_illisible") == ("echec", "cv_illisible")


def test_l_interruption_l_emporte_sur_le_code_stocke() -> None:
    assert _affiche("en_cours", 301, "cv_illisible") == ("echec", ANALYSE_INTERROMPUE)


def test_un_etat_inconnu_passe_tel_quel() -> None:
    """La règle ne valide pas : c'est le CHECK de la base qui garde la liste."""
    assert _affiche("inconnu", 100_000, "x") == ("inconnu", "x")
