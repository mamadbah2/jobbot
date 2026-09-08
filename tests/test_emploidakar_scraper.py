"""Branchement HTTP du scraper emploidakar (CLAUDE.md §7).

Le parsing est testé sur fixtures ailleurs ; ici on vérifie le contrat
réseau : le bon point d'entrée (`admin-ajax.php`, pas l'API REST sous
challenge Cloudflare), les bons paramètres WP Job Manager, et le fait que
les zones interdites par `robots.txt` restent inaccessibles.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import httpx
import pytest

from src.ingest.base import (
    CheminInterditError,
    PoliteClient,
    RawJob,
    StructureInattendueError,
)
from src.ingest.sources.emploidakar import URL_AJAX, EmploiDakarScraper

FIXTURES = Path(__file__).parent / "fixtures"
LISTE = json.loads((FIXTURES / "emploidakar_listings.json").read_text(encoding="utf-8"))
DETAIL = (FIXTURES / "emploidakar_detail.html").read_text(encoding="utf-8")
ROBOTS = (FIXTURES / "emploidakar_robots.txt").read_text(encoding="utf-8")


class SiteFactice:
    """emploidakar figé : aucune requête ne sort, tout vient des fixtures."""

    def __init__(self, *, liste: httpx.Response | None = None) -> None:
        self.requetes: list[httpx.Request] = []
        self._liste = liste

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requetes.append(request)
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text=ROBOTS)
        if request.url.path == "/wp-admin/admin-ajax.php":
            return self._liste if self._liste is not None else httpx.Response(200, json=LISTE)
        return httpx.Response(200, text=DETAIL)


def _scraper(site: SiteFactice) -> EmploiDakarScraper:
    async def dormir(_: float) -> None:
        return None

    client = PoliteClient(
        httpx.AsyncClient(transport=httpx.MockTransport(site)),
        user_agent="JobBotSN/0.1 (+contact: admin@example.sn)",
        delai=0.0,
        horloge=time.monotonic,
        dormir=dormir,
        chemins_interdits=EmploiDakarScraper.chemins_interdits,
    )
    return EmploiDakarScraper(client)


async def test_interroge_admin_ajax_avec_les_parametres_wp_job_manager() -> None:
    site = SiteFactice()
    page = await _scraper(site).fetch_list(2)
    envoyee = site.requetes[-1]
    assert envoyee.method == "POST"
    assert str(envoyee.url) == URL_AJAX
    corps = dict(pair.split("=", 1) for pair in envoyee.content.decode().split("&"))
    assert corps["action"] == "job_manager_get_listings"
    assert corps["page"] == "2"
    assert page.pages_totales == 14
    assert len(page.resultat.offres) == 17


async def test_n_utilise_jamais_l_api_rest_wordpress() -> None:
    """§7 : `/wp-json/` tombe sous challenge Cloudflare, ne pas y toucher."""
    site = SiteFactice()
    await _scraper(site).collecter(frozenset())
    assert not any("/wp-json/" in str(r.url) for r in site.requetes)


async def test_une_reponse_illisible_est_un_changement_de_structure() -> None:
    site = SiteFactice(liste=httpx.Response(200, text="<html>Oups</html>"))
    with pytest.raises(StructureInattendueError):
        await _scraper(site).fetch_list(1)


async def test_une_erreur_http_sur_la_liste_remonte() -> None:
    site = SiteFactice(liste=httpx.Response(500, text=""))
    with pytest.raises(httpx.HTTPStatusError):
        await _scraper(site).fetch_list(1)


async def test_la_cvtheque_reste_interdite() -> None:
    """§7 : /resume/, /CV/ et les candidatures déposées sont des données de tiers."""
    scraper = _scraper(SiteFactice())
    for chemin in ("/resume/x", "/CV/x", "/wp-content/uploads/job_applications/x.pdf"):
        offre = RawJob(
            source="emploidakar",
            source_id="1",
            url=f"https://www.emploidakar.com{chemin}",
            title="Piège",
        )
        with pytest.raises(CheminInterditError):
            await scraper.parse_detail(offre)


async def test_passe_complete_sur_les_fixtures() -> None:
    """Bout en bout hors réseau : liste, pagination, détail des nouveautés."""
    site = SiteFactice()
    scraper = _scraper(site)
    resultat = await scraper.collecter(frozenset())
    # La 2e page renvoie la même fixture : vue deux fois, mais dédoublonnée.
    assert resultat.offres_vues == 34
    assert len(resultat.offres) == 17
    assert resultat.bloquee is False
    # Page entièrement connue : la passe s'arrête là, sans parcourir les 14 pages.
    assert sum(1 for r in site.requetes if r.url.path == "/wp-admin/admin-ajax.php") == 2
    assert all(o.detail.description for o in resultat.offres)
