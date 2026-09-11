"""GET /moi, POST /auth/deconnexion, POST /moi/telegram/jeton (spec Phase 2 §9).

Lancer avec : RUN_INTEGRATION_TESTS=1 pytest -m integration

Les fixtures `client_auth` / `fournisseur_courriel_espion` et le helper
`demander_code_verification` vivent dans `tests/conftest.py` : ce fichier les
réutilise sans les recopier (amendement 2, tâche 14).
"""

from __future__ import annotations

from typing import Any
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient

from src.api.routers import moi
from src.config import get_settings
from tests.conftest import FauxCache, FournisseurCourrielEspion, demander_code_verification

ADRESSE = "fatou@jobbot-test.sn"
TEL = "+221771234567"


def _code(client: TestClient, espion: FournisseurCourrielEspion, adresse: str = ADRESSE) -> str:
    return demander_code_verification(client, espion, adresse)


class AlerteEspionne:
    """Capture les alertes admin, sans en émettre nulle part (round de
    correction 1, tâche 14) — même forme que celle de
    `tests/test_api_auth_demande.py`, non partagée : un seul appelant chacune."""

    def __init__(self) -> None:
        self.alertes: list[tuple[str, dict[str, Any]]] = []

    async def envoyer(self, evenement: str, **contexte: Any) -> None:
        self.alertes.append((evenement, contexte))


def _connecter(
    client: TestClient, espion: FournisseurCourrielEspion, adresse: str = ADRESSE
) -> None:
    code = _code(client, espion, adresse)
    client.post(
        "/auth/code/verifie",
        json={"email": adresse, "code": code, "telephone": TEL, "nom_complet": "Fatou"},
    )


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


@pytest.mark.integration
def test_jeton_de_liaison_sans_bot_configure_refuse_et_alerte(
    client_auth: TestClient, fournisseur_courriel_espion: FournisseurCourrielEspion
) -> None:
    """`TELEGRAM_BOT_USERNAME` vide (défaut) doit refuser bruyamment, pas
    produire un lien `https://t.me/?start=...` silencieusement mort
    (round de correction 1)."""
    assert get_settings().telegram_bot_username == ""
    espionnee = AlerteEspionne()
    client_auth.app.dependency_overrides[moi.alerte] = lambda: espionnee  # type: ignore[attr-defined]

    _connecter(client_auth, fournisseur_courriel_espion)
    r = client_auth.post("/moi/telegram/jeton")

    assert r.status_code == 503
    assert r.json()["erreur"] == "liaison_indisponible"
    assert espionnee.alertes == [("telegram_bot_username_absent", {})]


@pytest.mark.integration
def test_jeton_de_liaison_perime_le_precedent(
    client_auth: TestClient,
    fournisseur_courriel_espion: FournisseurCourrielEspion,
    faux_cache: FauxCache,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Un seul jeton de liaison valide à la fois : en redemander un périme
    l'ancien (round de correction 1)."""
    monkeypatch.setenv("TELEGRAM_BOT_USERNAME", "jobbot_sn_bot")
    get_settings.cache_clear()
    _connecter(client_auth, fournisseur_courriel_espion)

    def _jeton_du_lien(lien: str) -> str:
        return parse_qs(urlparse(lien).query)["start"][0]

    premier = _jeton_du_lien(client_auth.post("/moi/telegram/jeton").json()["lien"])
    second = _jeton_du_lien(client_auth.post("/moi/telegram/jeton").json()["lien"])

    assert premier != second
    assert f"jobbot:auth:liaison:{premier}" not in faux_cache.valeurs
    assert f"jobbot:auth:liaison:{second}" in faux_cache.valeurs


@pytest.mark.integration
def test_jeton_de_liaison_se_remet_d_un_pointeur_orphelin(
    client_auth: TestClient,
    fournisseur_courriel_espion: FournisseurCourrielEspion,
    faux_cache: FauxCache,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Simule un arrêt du processus entre l'écriture du pointeur et celle du
    jeton qu'il désigne : le pointeur survit, pointant vers un jeton qui n'a
    jamais existé en cache. L'émission suivante doit s'en remettre
    proprement, sans lever d'erreur (round de correction 2)."""
    monkeypatch.setenv("TELEGRAM_BOT_USERNAME", "jobbot_sn_bot")
    get_settings.cache_clear()
    _connecter(client_auth, fournisseur_courriel_espion)

    def _jeton_du_lien(lien: str) -> str:
        return parse_qs(urlparse(lien).query)["start"][0]

    premier = _jeton_du_lien(client_auth.post("/moi/telegram/jeton").json()["lien"])
    # Simule l'arrêt : le pointeur `liaison-actif` reste, mais le jeton
    # lui-même disparaît, comme si le processus était mort juste après avoir
    # écrit le pointeur et avant d'écrire le jeton.
    del faux_cache.valeurs[f"jobbot:auth:liaison:{premier}"]

    r = client_auth.post("/moi/telegram/jeton")
    assert r.status_code == 200
    second = _jeton_du_lien(r.json()["lien"])

    assert second != premier
    assert f"jobbot:auth:liaison:{premier}" not in faux_cache.valeurs
    assert f"jobbot:auth:liaison:{second}" in faux_cache.valeurs
