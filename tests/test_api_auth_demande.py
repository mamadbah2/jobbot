"""POST /auth/code/demande (spec Phase 2 §8)."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from structlog.testing import capture_logs

from src.api import deps
from src.api.app import create_app
from tests.conftest import FauxCache


class FournisseurEspion:
    def __init__(self) -> None:
        self.envois: list[tuple[str, str]] = []

    async def envoyer_code(self, destinataire: str, code: str) -> None:
        self.envois.append((destinataire, code))


class FournisseurEnPanne:
    """Simule un fournisseur réel qui échoue (round de correction 1, §3)."""

    async def envoyer_code(self, destinataire: str, code: str) -> None:
        raise RuntimeError("SMTP indisponible")


class FournisseurEnPanneAvecAdresseDansLeMessage:
    """Un fournisseur SMTP réel embarque souvent le destinataire dans son
    message d'erreur (round de correction 2) : « 550 no such user <adresse> »
    est un format de rejet courant."""

    async def envoyer_code(self, destinataire: str, code: str) -> None:
        raise RuntimeError(f"550 no such user <{destinataire}>")


class AlerteEspionne:
    def __init__(self) -> None:
        self.alertes: list[tuple[str, dict[str, Any]]] = []

    async def envoyer(self, evenement: str, **contexte: Any) -> None:
        self.alertes.append((evenement, contexte))


@pytest.fixture
def espion() -> FournisseurEspion:
    return FournisseurEspion()


@pytest.fixture
def client(espion: FournisseurEspion, faux_cache: FauxCache) -> Iterator[TestClient]:
    from src.api.routers import auth

    app = create_app()

    async def _cache() -> Any:
        yield faux_cache

    app.dependency_overrides[deps.cache_redis] = _cache
    app.dependency_overrides[auth.fournisseur] = lambda: espion
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


def test_demande_acceptee(client: TestClient, espion: FournisseurEspion) -> None:
    reponse = client.post("/auth/code/demande", json={"email": "fatou@example.sn"})
    assert reponse.status_code == 202
    assert len(espion.envois) == 1
    destinataire, code = espion.envois[0]
    assert destinataire == "fatou@example.sn"
    assert len(code) == 6 and code.isdigit()


def test_adresse_normalisee_avant_envoi(client: TestClient, espion: FournisseurEspion) -> None:
    client.post("/auth/code/demande", json={"email": "  Fatou@EXAMPLE.SN "})
    assert espion.envois[0][0] == "Fatou@example.sn"


def test_adresse_invalide_refusee(client: TestClient, espion: FournisseurEspion) -> None:
    reponse = client.post("/auth/code/demande", json={"email": "pas-une-adresse"})
    assert reponse.status_code == 422
    assert reponse.json()["erreur"] == "adresse_invalide"
    assert espion.envois == []


def test_reponse_identique_pour_adresse_connue_ou_non(client: TestClient) -> None:
    """Sinon l'endpoint dit publiquement qui est client (spec §8, règle n°1)."""
    a = client.post("/auth/code/demande", json={"email": "connue@example.sn"})
    b = client.post("/auth/code/demande", json={"email": "jamais.vue@example.sn"})
    assert (a.status_code, a.text) == (b.status_code, b.text)


def test_cooldown_applique(client: TestClient) -> None:
    client.post("/auth/code/demande", json={"email": "fatou@example.sn"})
    seconde = client.post("/auth/code/demande", json={"email": "fatou@example.sn"})
    assert seconde.status_code == 429
    assert seconde.headers["Retry-After"] == "60"


def test_le_code_n_est_jamais_dans_la_reponse(client: TestClient) -> None:
    reponse = client.post("/auth/code/demande", json={"email": "fatou@example.sn"})
    assert reponse.text.strip() in ("", "null")


def test_envoi_impossible_renvoie_503_et_alerte(faux_cache: FauxCache) -> None:
    """Un fournisseur en panne ne doit ni planter en 500 ni échouer en silence
    (round de correction 1, §3). Les compteurs déjà consommés ne sont pas
    remboursés : ce n'est pas ce que ce test vérifie."""
    from src.api.routers import auth

    app = create_app()
    alerte_espionnee = AlerteEspionne()

    async def _cache() -> Any:
        yield faux_cache

    app.dependency_overrides[deps.cache_redis] = _cache
    app.dependency_overrides[auth.fournisseur] = lambda: FournisseurEnPanne()
    app.dependency_overrides[auth.alerte] = lambda: alerte_espionnee

    with TestClient(app, raise_server_exceptions=False) as c:
        reponse = c.post("/auth/code/demande", json={"email": "fatou@example.sn"})

    assert reponse.status_code == 503
    assert reponse.json() == {"erreur": "envoi_impossible"}
    assert len(alerte_espionnee.alertes) == 1
    evenement, contexte = alerte_espionnee.alertes[0]
    assert evenement == "envoi_courriel_echoue"
    assert contexte == {"domaine": "example.sn"}


def test_message_erreur_fournisseur_jamais_journalise(faux_cache: FauxCache) -> None:
    """Round de correction 2 : un message d'erreur SMTP embarque couramment le
    destinataire (« 550 no such user <adresse> »). Verrouille la régression du
    round de correction 1, où `str(exc)` avait été journalisé tel quel."""
    from src.api.routers import auth

    app = create_app()
    adresse = "fatou@jobbot-test.sn"

    async def _cache() -> Any:
        yield faux_cache

    app.dependency_overrides[deps.cache_redis] = _cache
    app.dependency_overrides[auth.fournisseur] = (
        lambda: FournisseurEnPanneAvecAdresseDansLeMessage()
    )
    app.dependency_overrides[auth.alerte] = lambda: AlerteEspionne()

    with capture_logs() as journal, TestClient(app, raise_server_exceptions=False) as c:
        reponse = c.post("/auth/code/demande", json={"email": adresse})

    assert reponse.status_code == 503
    assert adresse not in reponse.text
    for entree in journal:
        assert adresse not in repr(entree)
