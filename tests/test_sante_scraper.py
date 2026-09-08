"""Détection d'un scraper cassé (CLAUDE.md §7).

« Si un scraper renvoie 0 offre alors qu'il en renvoyait > 0 la veille →
log ERROR + notification Telegram à l'admin. Ne jamais échouer en silence. »
"""

from __future__ import annotations

from src.ingest.base import scraper_semble_casse


def test_zero_offre_alors_que_la_base_en_contient_est_une_casse() -> None:
    assert scraper_semble_casse(offres_vues=0, offres_connues=238) is True


def test_une_passe_normale_n_est_pas_une_casse() -> None:
    assert scraper_semble_casse(offres_vues=17, offres_connues=238) is False


def test_zero_nouvelle_offre_n_est_pas_une_casse() -> None:
    """Le site peut ne rien publier pendant deux jours : les offres restent vues."""
    assert scraper_semble_casse(offres_vues=17, offres_connues=17) is False


def test_premiere_passe_a_vide_n_est_pas_qualifiee_de_regression() -> None:
    """Sans historique, on ne peut pas parler de régression : l'échec se voit ailleurs."""
    assert scraper_semble_casse(offres_vues=0, offres_connues=0) is False
