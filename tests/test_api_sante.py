"""Socle de l'API : /health et traduction des erreurs métier."""

from __future__ import annotations

from collections.abc import Iterator

from fastapi import APIRouter
from fastapi.testclient import TestClient

from src.api.app import TAILLE_CORPS_MAX, create_app
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


def _app_avec_echo() -> APIRouter:
    router = APIRouter()

    @router.post("/essai/echo")
    async def echo() -> dict[str, bool]:
        return {"ok": True}

    return router


def test_corps_trop_grand_refuse() -> None:
    """Le premier endpoint public non authentifié du produit ne doit pas laisser
    bufferiser des mégaoctets avant tout contrôle (round de correction 1, §2)."""
    app = create_app()
    app.include_router(_app_avec_echo())
    with TestClient(app, raise_server_exceptions=False) as client:
        r = client.post("/essai/echo", content=b"x" * (TAILLE_CORPS_MAX + 1))
    assert r.status_code == 413
    assert r.json() == {"erreur": "corps_trop_grand"}


def test_corps_sans_content_length_refuse() -> None:
    """Un Content-Length absent (ex. streaming) est refusé avant lecture du corps."""
    app = create_app()
    app.include_router(_app_avec_echo())

    def flux() -> Iterator[bytes]:
        yield b"{}"

    with TestClient(app, raise_server_exceptions=False) as client:
        r = client.post("/essai/echo", content=flux())
    assert r.status_code == 411
    assert r.json() == {"erreur": "longueur_requise"}


def test_content_length_non_numerique_refuse() -> None:
    """Un Content-Length qui n'est pas un entier est refusé, pas planté."""
    app = create_app()
    app.include_router(_app_avec_echo())
    with TestClient(app, raise_server_exceptions=False) as client:
        r = client.post(
            "/essai/echo", content=b"{}", headers={"content-length": "pas-un-nombre"}
        )
    assert r.status_code == 413
    assert r.json() == {"erreur": "corps_trop_grand"}


def test_corps_normal_toujours_accepte() -> None:
    app = create_app()
    app.include_router(_app_avec_echo())
    with TestClient(app, raise_server_exceptions=False) as client:
        r = client.post("/essai/echo", json={"a": 1})
    assert r.status_code == 200
    assert r.json() == {"ok": True}


def test_get_non_affecte_par_la_limite_de_corps() -> None:
    """Le contrôle ne porte que sur les méthodes avec corps (POST/PUT/PATCH)."""
    with TestClient(create_app(), raise_server_exceptions=False) as client:
        reponse = client.get("/health")
    assert reponse.status_code in (200, 503)
