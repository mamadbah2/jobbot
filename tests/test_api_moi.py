"""GET /moi, POST /auth/deconnexion, POST /moi/telegram/jeton (spec Phase 2 §9).

Lancer avec : RUN_INTEGRATION_TESTS=1 pytest -m integration

Les fixtures `client_auth` / `fournisseur_courriel_espion` et le helper
`demander_code_verification` vivent dans `tests/conftest.py` : ce fichier les
réutilise sans les recopier (amendement 2, tâche 14).
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from src.config import get_settings
from tests.conftest import FournisseurCourrielEspion, demander_code_verification

ADRESSE = "fatou@jobbot-test.sn"
TEL = "+221771234567"


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
        json={"email": ADRESSE, "code": code, "telephone": TEL, "nom_complet": "Fatou"},
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
        json={"email": ADRESSE, "code": code, "telephone": TEL, "nom_complet": "Fatou"},
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
        json={"email": ADRESSE, "code": code, "telephone": TEL, "nom_complet": "Fatou"},
    )
    jeton = r.cookies[get_settings().cookie_session_nom]
    assert client_auth.post("/auth/deconnexion").status_code == 204

    # Même en rejouant le jeton d'origine, l'accès est refusé.
    client_auth.cookies.set(get_settings().cookie_session_nom, jeton)
    assert client_auth.get("/moi").status_code == 401


@pytest.mark.integration
def test_jeton_de_liaison_telegram(
    client_auth: TestClient,
    fournisseur_courriel_espion: FournisseurCourrielEspion,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TELEGRAM_BOT_USERNAME", "jobbot_sn_bot")
    get_settings.cache_clear()
    code = _code(client_auth, fournisseur_courriel_espion)
    client_auth.post(
        "/auth/code/verifie",
        json={"email": ADRESSE, "code": code, "telephone": TEL, "nom_complet": "Fatou"},
    )
    r = client_auth.post("/moi/telegram/jeton")
    assert r.status_code == 200
    assert r.json()["lien"].startswith("https://t.me/jobbot_sn_bot?start=")
    assert r.json()["expire_dans"] == 600


@pytest.mark.integration
def test_jeton_de_liaison_exige_une_session(client_auth: TestClient) -> None:
    assert client_auth.post("/moi/telegram/jeton").status_code == 401
