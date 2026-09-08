"""Détection d'un changement de structure du site (CLAUDE.md §7).

Les fixtures figées détectent une régression de notre code, pas une refonte
du site : elles resteraient vertes pendant que la production ramène 0 offre.
Le garde-fou doit donc s'exécuter à chaque passe, sur les données réelles.
"""

from __future__ import annotations

import pytest

from src.ingest.base import StructureInattendueError, verifier_coherence_liste


def test_accepte_une_page_normale() -> None:
    verifier_coherence_liste(offres_lues=17, offres_ignorees=0, pages_annoncees=14)


def test_leve_si_le_site_annonce_des_offres_mais_qu_aucune_n_est_lue() -> None:
    """Symptôme n°1 d'une refonte : le HTML arrive mais plus aucun sélecteur ne matche."""
    with pytest.raises(StructureInattendueError):
        verifier_coherence_liste(offres_lues=0, offres_ignorees=0, pages_annoncees=14)


def test_leve_si_la_majorite_des_offres_est_ignoree() -> None:
    """Symptôme n°2 : structure changée à moitié, on perdrait la moitié des offres."""
    with pytest.raises(StructureInattendueError):
        verifier_coherence_liste(offres_lues=3, offres_ignorees=14, pages_annoncees=14)


def test_tolere_quelques_offres_ignorees() -> None:
    """Une annonce mal saisie par un recruteur ne doit pas arrêter l'ingestion."""
    verifier_coherence_liste(offres_lues=16, offres_ignorees=1, pages_annoncees=14)


def test_ne_leve_pas_quand_le_site_annonce_zero_page() -> None:
    """Recherche sans résultat : légitime, ce n'est pas une casse."""
    verifier_coherence_liste(offres_lues=0, offres_ignorees=0, pages_annoncees=0)
