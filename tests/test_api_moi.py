"""GET /moi et POST /auth/deconnexion (spec Phase 2 §9).

`POST /moi/telegram/jeton` a été retiré le 2026-09-12 avec le client Telegram.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from src.config import get_settings
from tests.conftest import FournisseurCourrielEspion, demander_code_verification

ADRESSE = "fatou@jobbot-test.sn"


def _code(client: TestClient, espion: FournisseurCourrielEspion, adresse: str = ADRESSE) -> str:
    return demander_code_verification(client, espion, adresse)


@pytest.mark.integration
def test_moi_sans_cookie_refuse(client_auth: TestClient) -> None:
    r = client_auth.get("/moi")
    assert r.status_code == 401
    assert r.json()["erreur"] == "jeton_invalide"


@pytest.mark.integration
def test_moi_avec_cookie(
    client_auth: TestClient, fournisseur_courriel_espion: FournisseurCourrielEspion
) -> None:
    code = _code(client_auth, fournisseur_courriel_espion)
    client_auth.post(
        "/auth/code/verifie",
        json={"email": ADRESSE, "code": code, "nom_complet": "Fatou"},
    )
    r = client_auth.get("/moi")
    assert r.status_code == 200
    assert r.json()["email"] == ADRESSE


@pytest.mark.integration
def test_jeton_bricole_refuse(
    client_auth: TestClient, fournisseur_courriel_espion: FournisseurCourrielEspion
) -> None:
    code = _code(client_auth, fournisseur_courriel_espion)
    client_auth.post(
        "/auth/code/verifie",
        json={"email": ADRESSE, "code": code, "nom_complet": "Fatou"},
    )
    client_auth.cookies.set(get_settings().cookie_session_nom, "pas.un.jeton")
    assert client_auth.get("/moi").status_code == 401


@pytest.mark.integration
def test_deconnexion_invalide_le_jeton(
    client_auth: TestClient, fournisseur_courriel_espion: FournisseurCourrielEspion
) -> None:
    """C'est tout l'intérêt de token_version : pas de table de sessions (spec §5)."""
    code = _code(client_auth, fournisseur_courriel_espion)
    r = client_auth.post(
        "/auth/code/verifie",
        json={"email": ADRESSE, "code": code, "nom_complet": "Fatou"},
    )
    jeton = r.cookies[get_settings().cookie_session_nom]
    assert client_auth.post("/auth/deconnexion").status_code == 204

    # Même en rejouant le jeton d'origine, l'accès est refusé.
    client_auth.cookies.set(get_settings().cookie_session_nom, jeton)
    assert client_auth.get("/moi").status_code == 401


@pytest.mark.integration
def test_l_endpoint_de_liaison_telegram_n_existe_plus(client_auth: TestClient) -> None:
    """L'endpoint produisait un lien profond `t.me`. Il est retiré avec le bot ;
    un 404 plutôt qu'un 401 prouve que la route elle-même a disparu, et pas
    seulement son autorisation."""
    assert client_auth.post("/moi/telegram/jeton").status_code == 404
