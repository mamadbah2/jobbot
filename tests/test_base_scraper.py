"""Boucle commune de `BaseScraper` (CLAUDE.md §7).

La classe porte ce qu'aucune source ne doit réécrire : pagination
incrémentale, contrôle de cohérence à chaque page, arrêt propre quand le
site oppose un challenge anti-bot, et lecture du `robots.txt` en début de
passe. Ces tests verrouillent ce contrat, indépendamment des sources.
"""

from __future__ import annotations

import time
from collections.abc import Set as AbstractSet

import httpx
import pytest

from src.ingest.base import (
    BaseScraper,
    CheminInterditError,
    JobDetail,
    PageListe,
    PoliteClient,
    RawJob,
    ResultatListe,
    SourceBloqueeError,
    StructureInattendueError,
)

ROBOTS = "User-agent: *\nDisallow: /prive/\n"


def _offre(identifiant: str) -> RawJob:
    return RawJob(
        source="factice",
        source_id=identifiant,
        url=f"https://exemple.sn/o/{identifiant}",
        title=f"Offre {identifiant}",
    )


def _page(ids: list[str], *, pages_totales: int, ignorees: int = 0) -> PageListe:
    return PageListe(
        resultat=ResultatListe(offres=tuple(_offre(i) for i in ids), ignorees=ignorees),
        pages_totales=pages_totales,
    )


def _client(robots: httpx.Response | None = None) -> PoliteClient:
    reponse_robots = robots if robots is not None else httpx.Response(200, text=ROBOTS)

    def repondre(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return reponse_robots
        return httpx.Response(200, text="ok")

    async def dormir(_: float) -> None:
        return None

    return PoliteClient(
        httpx.AsyncClient(transport=httpx.MockTransport(repondre)),
        user_agent="JobBotSN/0.1",
        delai=0.0,
        horloge=time.monotonic,
        dormir=dormir,
        chemins_interdits=("/resume/",),
    )


class ScraperFactice(BaseScraper):
    """Source de test : aucun réseau, des pages décidées à l'avance."""

    source = "factice"
    domaine = "exemple.sn"
    url_robots = "https://exemple.sn/robots.txt"

    def __init__(
        self,
        client: PoliteClient,
        pages: dict[int, PageListe | Exception],
        *,
        details_en_erreur: AbstractSet[str] = frozenset(),
    ) -> None:
        super().__init__(client)
        self._pages = pages
        self._details_en_erreur = details_en_erreur
        self.pages_demandees: list[int] = []
        self.details_demandes: list[str] = []

    async def fetch_list(self, page: int) -> PageListe:
        self.pages_demandees.append(page)
        reponse = self._pages[page]
        if isinstance(reponse, Exception):
            raise reponse
        return reponse

    async def parse_detail(self, offre: RawJob) -> JobDetail:
        self.details_demandes.append(offre.source_id)
        if offre.source_id in self._details_en_erreur:
            raise httpx.ConnectError("détail injoignable")
        return JobDetail(description=f"description {offre.source_id}")


async def test_parcourt_les_pages_tant_qu_elles_apportent_du_nouveau() -> None:
    scraper = ScraperFactice(
        _client(),
        {
            1: _page(["1", "2"], pages_totales=3),
            2: _page(["3", "4"], pages_totales=3),
            3: _page(["5"], pages_totales=3),
        },
    )
    resultat = await scraper.collecter(frozenset())
    assert scraper.pages_demandees == [1, 2, 3]
    assert [o.brut.source_id for o in resultat.offres] == ["1", "2", "3", "4", "5"]


async def test_s_arrete_sur_une_page_entierement_connue() -> None:
    """Signal d'arrêt de §7 : une page sans aucune nouveauté, pas une offre connue."""
    scraper = ScraperFactice(
        _client(),
        {
            1: _page(["1", "2"], pages_totales=5),
            2: _page(["3", "4"], pages_totales=5),
            3: _page(["5"], pages_totales=5),
        },
    )
    resultat = await scraper.collecter({"3", "4"})
    assert scraper.pages_demandees == [1, 2]
    assert [o.brut.source_id for o in resultat.offres] == ["1", "2"]


async def test_n_ouvre_le_detail_que_des_offres_nouvelles() -> None:
    """Rouvrir les annonces déjà en base coûte du temps et des requêtes chez un tiers."""
    scraper = ScraperFactice(_client(), {1: _page(["1", "2", "3"], pages_totales=1)})
    await scraper.collecter({"2"})
    assert scraper.details_demandes == ["1", "3"]


async def test_ne_depasse_pas_le_nombre_de_pages_annonce() -> None:
    scraper = ScraperFactice(_client(), {1: _page(["1", "2"], pages_totales=1)})
    await scraper.collecter(frozenset())
    assert scraper.pages_demandees == [1]


async def test_ne_redemande_pas_une_offre_vue_sur_une_page_precedente() -> None:
    """La dérive de pagination peut faire réapparaître une offre à la page suivante."""
    scraper = ScraperFactice(
        _client(),
        {
            1: _page(["1", "2"], pages_totales=2),
            2: _page(["2", "3"], pages_totales=2),
        },
    )
    resultat = await scraper.collecter(frozenset())
    assert scraper.details_demandes == ["1", "2", "3"]
    assert len(resultat.offres) == 3


async def test_arret_propre_quand_le_site_oppose_un_challenge() -> None:
    """§2.4 : on n'insiste pas, on garde ce qui est déjà lu et on signale."""
    scraper = ScraperFactice(
        _client(),
        {
            1: _page(["1"], pages_totales=3),
            2: SourceBloqueeError("challenge anti-bot sur exemple.sn"),
        },
    )
    resultat = await scraper.collecter(frozenset())
    assert resultat.bloquee is True
    assert [o.brut.source_id for o in resultat.offres] == ["1"]
    assert scraper.pages_demandees == [1, 2]


async def test_verifie_la_coherence_de_chaque_page() -> None:
    """Une page annoncée pleine mais illisible = refonte du site (§7)."""
    scraper = ScraperFactice(_client(), {1: _page([], pages_totales=14)})
    with pytest.raises(StructureInattendueError):
        await scraper.collecter(frozenset())


async def test_une_page_de_detail_injoignable_ne_perd_pas_la_passe() -> None:
    scraper = ScraperFactice(
        _client(),
        {1: _page(["1", "2"], pages_totales=1)},
        details_en_erreur={"1"},
    )
    resultat = await scraper.collecter(frozenset())
    assert [o.brut.source_id for o in resultat.offres] == ["2"]


async def test_charge_le_robots_txt_au_debut_de_la_passe() -> None:
    """§2.4 : les règles du site sont relues à chaque passe, pas figées au déploiement."""
    client = _client()
    scraper = ScraperFactice(client, {1: _page(["1"], pages_totales=1)})
    await scraper.collecter(frozenset())
    with pytest.raises(CheminInterditError):
        await client.get("https://exemple.sn/prive/x")


async def test_la_liste_noire_tient_si_robots_txt_est_injoignable() -> None:
    """Plancher de §7 : /resume/ reste refusé même sans robots.txt."""
    client = _client(robots=httpx.Response(500, text=""))
    scraper = ScraperFactice(client, {1: _page(["1"], pages_totales=1)})
    resultat = await scraper.collecter(frozenset())
    assert len(resultat.offres) == 1
    with pytest.raises(CheminInterditError):
        await client.get("https://exemple.sn/resume/x")


async def test_compte_les_offres_vues_pour_le_detecteur_de_casse() -> None:
    """`offres_vues` compte ce que le site a rendu, connu ou non (§7)."""
    scraper = ScraperFactice(_client(), {1: _page(["1", "2", "3"], pages_totales=1)})
    resultat = await scraper.collecter({"1", "2", "3"})
    assert resultat.offres_vues == 3
    assert resultat.offres == ()
