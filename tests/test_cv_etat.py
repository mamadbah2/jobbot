"""Règle de péremption d'une analyse (spec §6)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from src.core.cv_etat import ANALYSE_INTERROMPUE, etat_affiche

MAINTENANT = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)


def test_une_analyse_recente_reste_en_cours() -> None:
    assert etat_affiche(
        "en_cours",
        MAINTENANT - timedelta(seconds=10),
        maintenant=MAINTENANT,
        delai_max_secondes=300,
    ) == ("en_cours", None)


def test_une_analyse_trop_vieille_devient_un_echec() -> None:
    """Le cas réel : `api` a redémarré, personne ne reprendra le travail."""
    assert etat_affiche(
        "en_cours",
        MAINTENANT - timedelta(seconds=301),
        maintenant=MAINTENANT,
        delai_max_secondes=300,
    ) == ("echec", ANALYSE_INTERROMPUE)


def test_en_cours_sans_date_de_depart_est_suspect() -> None:
    assert etat_affiche(
        "en_cours", None, maintenant=MAINTENANT, delai_max_secondes=300
    ) == ("echec", ANALYSE_INTERROMPUE)


def test_les_autres_etats_passent_sans_etre_touches() -> None:
    for etat in ("en_attente", "pret", "echec"):
        assert etat_affiche(
            etat, None, maintenant=MAINTENANT, delai_max_secondes=300
        ) == (etat, None)
