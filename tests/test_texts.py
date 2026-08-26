"""Garde-fous UX (CLAUDE.md §6 et §11) : brièveté et vouvoiement."""

from __future__ import annotations

import re

import pytest

from src.bot import texts

TOUS_LES_TEXTES = {
    nom: valeur for nom, valeur in vars(texts).items() if nom.isupper() and isinstance(valeur, str)
}

# Marqueurs de tutoiement. On cherche des mots entiers pour éviter les faux
# positifs (« votre », « ton » dans « bâton », etc.).
TUTOIEMENT = re.compile(r"\b(tu|ton|ta|tes|toi|t'as)\b|\b\w+(?<!v)ez-tu\b", re.IGNORECASE)


def test_start_tient_en_trois_lignes() -> None:
    """§6 : la présentation de /start fait 3 lignes maximum."""
    assert len(texts.START.strip().splitlines()) <= 3


def test_start_ne_demande_pas_de_paiement() -> None:
    """§6 : la valeur doit être visible avant toute demande de paiement."""
    interdits = ("fcfa", "abonnement", "payer", "paiement", "prix")
    assert not any(mot in texts.START.lower() for mot in interdits)


@pytest.mark.parametrize("nom", sorted(TOUS_LES_TEXTES))
def test_vouvoiement_partout(nom: str) -> None:
    """§11 : vouvoiement cohérent, jamais mélangé avec du tutoiement."""
    assert not TUTOIEMENT.search(TOUS_LES_TEXTES[nom]), f"tutoiement détecté dans {nom}"


@pytest.mark.parametrize("nom", sorted(TOUS_LES_TEXTES))
def test_pas_de_jargon_rh(nom: str) -> None:
    """§11 : français simple. « employabilité » et consorts sont proscrits."""
    jargon = ("employabilité", "synergie", "proactivité", "upskilling")
    texte = TOUS_LES_TEXTES[nom].lower()
    assert not any(mot in texte for mot in jargon), f"jargon détecté dans {nom}"


def test_aide_liste_les_commandes() -> None:
    """§11 : /aide est toujours disponible et doit s'auto-documenter."""
    assert "/start" in texts.AIDE
    assert "/aide" in texts.AIDE
