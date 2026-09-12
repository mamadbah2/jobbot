"""Passe d'ingestion du worker (CLAUDE.md §4 et §7).

Ce qui est vérifié ici : la pagination est bien alimentée par les offres déjà
en base, les nouveautés sont écrites, et aucune anomalie ne passe en silence
(scraper cassé, source bloquée, structure changée).
"""

from __future__ import annotations

from collections.abc import Iterable
from collections.abc import Set as AbstractSet
from typing import Any

from structlog.testing import capture_logs

from src.config import get_settings
from src.ingest.base import (
    BaseScraper,
    JobDetail,
    OffreComplete,
    PageListe,
    RawJob,
    ResultatPasse,
    StructureInattendueError,
)
from src.ingest.sources.emploidakar import EmploiDakarScraper
from src.ingest.store import ResultatEcriture
from src.worker_ingest import construire_client, ingerer_source


def _offre(identifiant: str, *, email: str | None = None) -> OffreComplete:
    return OffreComplete(
        brut=RawJob(
            source="factice",
            source_id=identifiant,
            url=f"https://exemple.sn/o/{identifiant}",
            title=f"Offre {identifiant}",
        ),
        detail=JobDetail(
            description="description",
            apply_email=email,
            apply_method="email" if email else "form",
        ),
    )


def _passe(
    offres: tuple[OffreComplete, ...] = (),
    *,
    offres_vues: int = 0,
    bloquee: bool = False,
) -> ResultatPasse:
    return ResultatPasse(
        offres=offres,
        offres_vues=offres_vues or len(offres),
        ignorees=0,
        pages_parcourues=1,
        bloquee=bloquee,
    )


class ScraperDouble(BaseScraper):
    """Scraper dont on décide le résultat de passe : aucun réseau."""

    source = "factice"
    domaine = "exemple.sn"
    url_robots = "https://exemple.sn/robots.txt"

    def __init__(self, resultat: ResultatPasse | Exception) -> None:
        self._resultat = resultat
        self.ids_recus: set[str] | None = None

    async def fetch_list(self, page: int) -> PageListe:  # pragma: no cover - non sollicité
        raise AssertionError("la boucle de pagination n'est pas testée ici")

    async def parse_detail(self, offre: RawJob) -> JobDetail:  # pragma: no cover
        raise AssertionError("la boucle de pagination n'est pas testée ici")

    async def collecter(self, ids_connus: AbstractSet[str]) -> ResultatPasse:
        self.ids_recus = set(ids_connus)
        if isinstance(self._resultat, Exception):
            raise self._resultat
        return self._resultat


class DepotFactice:
    def __init__(self, ids: AbstractSet[str] = frozenset()) -> None:
        self._ids = set(ids)
        self.ecrites: list[OffreComplete] = []

    async def ids_connus(self, source: str) -> set[str]:
        return set(self._ids)

    async def enregistrer(self, offres: Iterable[OffreComplete]) -> ResultatEcriture:
        recues = list(offres)
        self.ecrites.extend(recues)
        return ResultatEcriture(ecrites=len(recues), ignorees=0)


class AlerteFactice:
    def __init__(self) -> None:
        self.envoyees: list[tuple[str, dict[str, Any]]] = []

    async def envoyer(self, evenement: str, **contexte: Any) -> None:
        self.envoyees.append((evenement, contexte))


def test_le_client_annonce_un_user_agent_identifiable() -> None:
    """§2, interdiction n°4 : jamais de User-Agent de navigateur usurpé."""
    client = construire_client(EmploiDakarScraper, get_settings())
    assert client.user_agent == get_settings().scraper_user_agent
    assert "mozilla" not in client.user_agent.lower()


def test_le_delai_respecte_le_plancher_de_la_source() -> None:
    """§7 : le rythme validé sur emploidakar est de 5 à 8 s, pas les 4 s par défaut."""
    settings = get_settings()
    assert settings.scraper_delay_seconds < EmploiDakarScraper.delai_minimum
    assert construire_client(EmploiDakarScraper, settings).delai >= 5.0


def test_une_source_sans_plancher_garde_le_delai_configure() -> None:
    assert construire_client(ScraperDouble, get_settings()).delai == 4.0


async def test_alimente_la_pagination_avec_les_offres_deja_en_base() -> None:
    """§7 : sans les identifiants connus, la passe rouvrirait les 238 annonces."""
    scraper = ScraperDouble(_passe())
    await ingerer_source(scraper, DepotFactice({"1", "2"}), AlerteFactice())
    assert scraper.ids_recus == {"1", "2"}


async def test_ecrit_les_offres_nouvelles() -> None:
    depot = DepotFactice()
    scraper = ScraperDouble(_passe((_offre("1"), _offre("2"))))
    bilan = await ingerer_source(scraper, depot, AlerteFactice())
    assert [o.brut.source_id for o in depot.ecrites] == ["1", "2"]
    assert bilan.ecrites == 2


async def test_compte_les_offres_avec_email_de_candidature() -> None:
    """Chiffre demandé par §7 : la part d'annonces réellement auto-soumissibles."""
    depot = DepotFactice()
    bilan = await ingerer_source(
        ScraperDouble(_passe((_offre("1", email="rh@acme.sn"), _offre("2")))),
        depot,
        AlerteFactice(),
    )
    assert bilan.avec_email == 1


async def test_alerte_quand_le_scraper_ne_ramene_plus_rien() -> None:
    """§7 : 0 offre alors que la base en contient → ERROR + alerte admin."""
    alerte = AlerteFactice()
    with capture_logs() as journal:
        bilan = await ingerer_source(ScraperDouble(_passe()), DepotFactice({"1"}), alerte)
    assert bilan.casse is True
    assert [e for e, _ in alerte.envoyees] == ["scraper_casse"]
    assert any(e["log_level"] == "error" for e in journal)


async def test_une_passe_normale_n_alerte_pas() -> None:
    alerte = AlerteFactice()
    bilan = await ingerer_source(ScraperDouble(_passe((_offre("1"),))), DepotFactice({"9"}), alerte)
    assert alerte.envoyees == []
    assert bilan.casse is False


async def test_alerte_quand_la_source_est_bloquee() -> None:
    """§2.4 : un challenge anti-bot doit remonter, on n'insiste pas."""
    alerte = AlerteFactice()
    bilan = await ingerer_source(
        ScraperDouble(_passe(bloquee=True)), DepotFactice({"1"}), alerte
    )
    assert bilan.bloquee is True
    assert [e for e, _ in alerte.envoyees] == ["source_bloquee"]


async def test_ecrit_quand_meme_ce_qui_a_ete_lu_avant_le_blocage() -> None:
    depot = DepotFactice()
    await ingerer_source(
        ScraperDouble(_passe((_offre("1"),), bloquee=True)), depot, AlerteFactice()
    )
    assert len(depot.ecrites) == 1


async def test_alerte_sur_un_changement_de_structure_du_site() -> None:
    """§7 : les fixtures figées ne voient pas une refonte, la passe si."""
    alerte = AlerteFactice()
    depot = DepotFactice({"1"})
    with capture_logs() as journal:
        bilan = await ingerer_source(
            ScraperDouble(StructureInattendueError("plus aucune offre lue")), depot, alerte
        )
    assert bilan.casse is True
    assert [e for e, _ in alerte.envoyees] == ["structure_inattendue"]
    assert any(e["log_level"] == "error" for e in journal)
    assert depot.ecrites == []


# --- Configuration du client de production (§2.4) ---


def test_le_client_de_production_ne_suit_pas_les_redirections() -> None:
    """Aucun test ne figeait cette option : le client réel la contredisait."""
    from src.config import Settings
    from src.ingest.sources.emploidakar import EmploiDakarScraper
    from src.worker_ingest import construire_client

    settings = Settings()  # type: ignore[call-arg]
    poli = construire_client(EmploiDakarScraper, settings)
    assert poli._client.follow_redirects is False


async def test_le_client_de_production_refuse_un_hote_etranger() -> None:
    """Les URL d'annonces sortent d'un href du site : périmètre verrouillé."""
    import pytest

    from src.config import Settings
    from src.ingest.base import CheminInterditError
    from src.ingest.sources.emploidakar import EmploiDakarScraper
    from src.worker_ingest import construire_client

    settings = Settings()  # type: ignore[call-arg]
    poli = construire_client(EmploiDakarScraper, settings)
    with pytest.raises(CheminInterditError):
        await poli.get("https://collecteur-externe.example/exfiltration?d=1")
