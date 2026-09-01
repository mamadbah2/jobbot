"""Extraction de l'email de candidature (CLAUDE.md §7).

C'est le cœur de la valeur : un email manqué = une candidature qui bascule en
mode brouillon ; un email erroné = une candidature envoyée dans le vide.
"""

from __future__ import annotations

import pytest

from src.ingest.normalize import extract_apply_email

DOMAINE = "emploidakar.com"


def test_extrait_email_dans_une_phrase_de_candidature() -> None:
    texte = "Envoyez CV + lettre de motivation à recrutement@xyz.sn avant le 30 juin."
    assert extract_apply_email(texte, DOMAINE) == "recrutement@xyz.sn"


def test_retourne_none_sans_email() -> None:
    texte = "Postulez directement via le formulaire en ligne."
    assert extract_apply_email(texte, DOMAINE) is None


def test_rejette_les_emails_du_portail_lui_meme() -> None:
    """§7 : un email du site n'est pas l'email du recruteur."""
    texte = "Pour toute question, contact@emploidakar.com."
    assert extract_apply_email(texte, DOMAINE) is None


@pytest.mark.parametrize(
    "adresse",
    ["webmaster@site.sn", "noreply@site.sn", "no-reply@site.sn", "postmaster@site.sn"],
)
def test_rejette_les_boites_generiques_non_humaines(adresse: str) -> None:
    """§7 : ces boîtes ne lisent pas de candidatures."""
    assert extract_apply_email(f"Ecrire à {adresse}", DOMAINE) is None


def test_prefere_une_adresse_de_recrutement_quand_plusieurs_sont_presentes() -> None:
    texte = "Infos: info@xyz.sn. Candidatures: recrutement@xyz.sn."
    assert extract_apply_email(texte, DOMAINE) == "recrutement@xyz.sn"


def test_ignore_les_faux_positifs_de_type_fichier() -> None:
    """Les noms de fichiers avec @ (retina, versions) ne sont pas des emails."""
    texte = "<img src='logo@2x.png'> Candidatures à rh@xyz.sn"
    assert extract_apply_email(texte, DOMAINE) == "rh@xyz.sn"


def test_normalise_la_casse_et_la_ponctuation_finale() -> None:
    texte = "Merci d'adresser votre dossier à RECRUTEMENT@XYZ.SN."
    assert extract_apply_email(texte, DOMAINE) == "recrutement@xyz.sn"
