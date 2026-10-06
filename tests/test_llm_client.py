"""Calcul du coût d'un appel DeepSeek, et robustesse du client.

Tarifs relevés le 2026-10-06 sur l'API officielle. Ils sont DATÉS : si le test
échoue un jour parce que DeepSeek a changé sa grille, c'est le test qui dit la
vérité sur ce qu'on croyait, pas la grille qui a tort.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from src.llm.client import calculer_cout

HORS_POINTE = datetime(2026, 10, 1, 14, 0, tzinfo=UTC)  # mercredi 14h UTC
EN_POINTE = datetime(2026, 10, 1, 7, 0, tzinfo=UTC)  # mercredi 7h UTC
WEEKEND_MEME_HEURE = datetime(2026, 10, 3, 7, 0, tzinfo=UTC)  # samedi 7h UTC


def test_le_cache_coute_cinquante_fois_moins_que_lentree_fraiche() -> None:
    """Confondre les deux fausse le suivi de coût massivement."""
    cache = calculer_cout("deepseek-flash", 1_000_000, 0, 0, moment=HORS_POINTE)
    frais = calculer_cout("deepseek-flash", 0, 1_000_000, 0, moment=HORS_POINTE)
    assert cache == Decimal("0.003")
    assert frais == Decimal("0.15")


def test_le_tarif_de_pointe_double_tout() -> None:
    creux = calculer_cout("deepseek-flash", 0, 1_000_000, 1_000_000, moment=HORS_POINTE)
    pointe = calculer_cout("deepseek-flash", 0, 1_000_000, 1_000_000, moment=EN_POINTE)
    assert pointe == creux * 2


def test_le_week_end_nest_jamais_en_pointe() -> None:
    """Les heures de pointe sont du lundi au vendredi : un calcul qui ne
    regarde que l'heure surfacture tout le week-end."""
    assert calculer_cout(
        "deepseek-flash", 0, 1_000_000, 0, moment=WEEKEND_MEME_HEURE
    ) == Decimal("0.15")


def test_la_grille_complete_au_centime() -> None:
    """Toute la grille relevée le 2026-10-06, sortie comprise, pour les deux modèles."""
    assert calculer_cout(
        "deepseek-flash", 0, 0, 1_000_000, moment=HORS_POINTE
    ) == Decimal("0.6")
    assert calculer_cout(
        "deepseek-v4-pro", 1_000_000, 0, 0, moment=HORS_POINTE
    ) == Decimal("0.022")
    assert calculer_cout(
        "deepseek-v4-pro", 0, 1_000_000, 0, moment=HORS_POINTE
    ) == Decimal("0.66")
    assert calculer_cout(
        "deepseek-v4-pro", 0, 0, 1_000_000, moment=HORS_POINTE
    ) == Decimal("1.98")


def test_les_bornes_des_heures_de_pointe() -> None:
    """01:00-04:00 et 06:00-10:00 : 04:00 et 10:00 sont déjà hors pointe,
    00:xx et 05:xx aussi."""
    cas = [(0, 1), (1, 2), (3, 2), (4, 1), (5, 1), (6, 2), (9, 2), (10, 1)]
    for heure, facteur in cas:
        moment = datetime(2026, 10, 1, heure, 0, tzinfo=UTC)
        cout = calculer_cout("deepseek-flash", 0, 1_000_000, 0, moment=moment)
        assert cout == Decimal("0.15") * facteur, heure


def test_le_modele_pro_est_plus_cher_que_flash() -> None:
    flash = calculer_cout("deepseek-flash", 0, 1_000_000, 0, moment=HORS_POINTE)
    pro = calculer_cout("deepseek-v4-pro", 0, 1_000_000, 0, moment=HORS_POINTE)
    assert pro > flash


def test_un_modele_inconnu_est_refuse_plutot_que_facture_a_zero() -> None:
    """Un tarif inconnu facturé 0 ferait croire que le produit ne coûte rien —
    exactement l'erreur qu'on ne verrait jamais dans un tableau de bord."""
    with pytest.raises(ValueError):
        calculer_cout("modele-invente", 0, 1000, 0, moment=HORS_POINTE)


def test_un_cv_coute_moins_que_le_plafond_du_brief() -> None:
    """Le §9 fixe 15 FCFA par candidature. Ordre de grandeur d'un CV :
    2 000 tokens en entrée, 1 500 en sortie."""
    cout_usd = calculer_cout("deepseek-flash", 0, 2000, 1500, moment=EN_POINTE)
    assert cout_usd * 600 < Decimal("15")  # ~600 FCFA pour 1 USD
