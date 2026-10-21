"""Forme de `profiles` après la Phase 3."""

from __future__ import annotations

from src.db.models import PARSE_ETATS, Profile


def test_les_etats_de_parsing_sont_clos() -> None:
    """Quatre états, pas plus : l'écran du profil les traite tous (spec §6)."""
    assert PARSE_ETATS == ("en_attente", "en_cours", "pret", "echec")


def test_le_chemin_du_fichier_a_disparu() -> None:
    """Le fichier d'origine n'est jamais conservé (décision du 2026-10-01).
    Une colonne qui promet un fichier qu'on ne stocke pas est un piège."""
    assert not hasattr(Profile, "cv_file_path")


def test_les_colonnes_de_parsing_existent() -> None:
    for nom in ("parse_etat", "parse_erreur", "parse_demarre_le"):
        assert hasattr(Profile, nom), nom
