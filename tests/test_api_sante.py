"""Socle de l'API : /health et traduction des erreurs métier."""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.testclient import TestClient

from src.api.app import create_app
from src.core.erreurs import CodeInvalide, PlafondGlobalAtteint, TropDeDemandes


def test_health_repond() -> None:
    """Postgres et Redis sont absents en test : /health répond 503, pas 500."""
    with TestClient(create_app(), raise_server_exceptions=False) as client:
        reponse = client.get("/health")
    assert reponse.status_code in (200, 503)
    assert "checks" in reponse.json()


def test_erreur_metier_traduite_en_http() -> None:
    app = create_app()
    router = APIRouter()

    @router.get("/essai/invalide")
    async def invalide() -> None:
        raise CodeInvalide(CodeInvalide.code)

    @router.get("/essai/trop")
    async def trop() -> None:
        raise TropDeDemandes(attendre_secondes=60)

    @router.get("/essai/plafond")
    async def plafond() -> None:
        raise PlafondGlobalAtteint(PlafondGlobalAtteint.code)

    app.include_router(router)
    with TestClient(app, raise_server_exceptions=False) as client:
        r = client.get("/essai/invalide")
        assert r.status_code == 400
        assert r.json() == {"erreur": "code_invalide"}

        r = client.get("/essai/trop")
        assert r.status_code == 429
        assert r.json()["erreur"] == "trop_de_demandes"
        assert r.headers["Retry-After"] == "60"

        r = client.get("/essai/plafond")
        assert r.status_code == 503


def test_documentation_desactivee() -> None:
    """Pas de /docs public : ça expose la surface d'attaque sans rien apporter ici."""
    with TestClient(create_app(), raise_server_exceptions=False) as client:
        assert client.get("/docs").status_code == 404
        assert client.get("/openapi.json").status_code == 404
