"""Scraper emploidakar.com (CLAUDE.md §7, source prioritaire n°1).

Les fixtures sont figées : si ces tests cassent, c'est que le site a changé de
structure — c'est précisément le signal qu'on veut (§7).
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from src.ingest.sources import emploidakar

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def payload_liste() -> dict[str, object]:
    return json.loads((FIXTURES / "emploidakar_listings.json").read_text(encoding="utf-8"))


@pytest.fixture
def html_detail() -> str:
    return (FIXTURES / "emploidakar_detail.html").read_text(encoding="utf-8")


def test_parse_list_retourne_toutes_les_offres_de_la_page(payload_liste: dict[str, object]) -> None:
    assert len(emploidakar.parse_list(payload_liste).offres) == 17


def test_parse_list_extrait_les_champs_de_l_offre(payload_liste: dict[str, object]) -> None:
    offre = emploidakar.parse_list(payload_liste).offres[0]
    assert offre.source == "emploidakar"
    assert offre.source_id == "503219"
    assert offre.url.startswith("https://www.emploidakar.com/offre-demploi/")
    assert offre.title == "Animateur commercial sénior"
    assert offre.company == "RH"
    assert offre.location == "DAKAR"
    assert offre.contract_type == "Prestation de Services"


def test_parse_list_sans_offre_retourne_une_liste_vide() -> None:
    payload = {"found_jobs": False, "html": "", "max_num_pages": 0}
    assert emploidakar.parse_list(payload).offres == ()


def test_nombre_de_pages_lit_la_pagination(payload_liste: dict[str, object]) -> None:
    assert emploidakar.nombre_de_pages(payload_liste) == 14


def test_parse_detail_extrait_description_date_et_email(html_detail: str) -> None:
    detail = emploidakar.parse_detail(html_detail)
    assert "Résumé du Poste" in detail.description
    assert detail.posted_at is not None and detail.posted_at.date() == date(2026, 9, 1)
    assert detail.apply_email == "recrutement.rh@css.sn"


def test_parse_detail_marque_apply_method_email_quand_un_email_existe(html_detail: str) -> None:
    """§7 : un email extractible rend l'auto-submit possible."""
    assert emploidakar.parse_detail(html_detail).apply_method == "email"


def test_parse_detail_bascule_en_form_sans_email() -> None:
    """§7 : sans email, mode brouillon obligatoire."""
    html = "<div class='job_description'>Postulez via le formulaire.</div>"
    detail = emploidakar.parse_detail(html)
    assert detail.apply_email is None
    assert detail.apply_method == "form"


def test_parse_detail_ignore_les_emails_du_portail() -> None:
    """§7 : contact@emploidakar.com n'est pas l'email du recruteur."""
    html = "<div class='job_description'>Ecrire à contact@emploidakar.com</div>"
    assert emploidakar.parse_detail(html).apply_email is None
