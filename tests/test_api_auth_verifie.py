"""POST /auth/code/verifie (spec Phase 2 §8).

Lancer avec : RUN_INTEGRATION_TESTS=1 pytest -m integration

Les fixtures `client_auth` / `fournisseur_courriel_espion` et le helper
`demander_code_verification` vivent dans `tests/conftest.py` : la tâche 14 les
réutilise sans les recopier.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from src.config import get_settings
from src.core.auth import cles, jetons
from tests.conftest import FournisseurCourrielEspion, demander_code_verification

ADRESSE = "fatou@jobbot-test.sn"
TEL = "+221771234567"


def _code(client: TestClient, espion: FournisseurCourrielEspion, adresse: str = ADRESSE) -> str:
    return demander_code_verification(client, espion, adresse)


@pytest.fixture(autouse=True)
def _sans_cooldown_demande(monkeypatch: pytest.MonkeyPatch) -> None:
    """Plusieurs tests de ce module (reconnexion, plafond de vérification par
    IP) enchaînent plusieurs `/auth/code/demande` pour la même adresse dans un
    même test. Le cooldown de cet endpoint (§10, garde-fou distinct du
    plafond de VÉRIFICATION testé ici) n'a pas sa place dans ces scénarios.
    """
    monkeypatch.setenv("AUTH_COOLDOWN_SECONDES", "0")
    get_settings.cache_clear()


@pytest.mark.integration
def test_inscription_complete(
    client_auth: TestClient, fournisseur_courriel_espion: FournisseurCourrielEspion
) -> None:
    code = _code(client_auth, fournisseur_courriel_espion)
    r = client_auth.post(
        "/auth/code/verifie",
        json={"email": ADRESSE, "code": code, "telephone": "77 123 45 67",
              "nom_complet": "Fatou Diop"},
    )
    assert r.status_code == 200
    corps = r.json()
    assert corps["email"] == ADRESSE
    assert corps["telephone"] == TEL
    assert corps["telegram_lie"] is False
    assert get_settings().cookie_session_nom in r.cookies


@pytest.mark.integration
def test_le_cookie_est_httponly(
    client_auth: TestClient, fournisseur_courriel_espion: FournisseurCourrielEspion
) -> None:
    """Un cookie lisible en JS est volable par n'importe quelle faille XSS."""
    code = _code(client_auth, fournisseur_courriel_espion)
    r = client_auth.post(
        "/auth/code/verifie",
        json={"email": ADRESSE, "code": code, "telephone": TEL, "nom_complet": "Fatou"},
    )
    entete = r.headers["set-cookie"].lower()
    assert "httponly" in entete
    assert "samesite=lax" in entete


@pytest.mark.integration
def test_le_jeton_porte_le_compte(
    client_auth: TestClient, fournisseur_courriel_espion: FournisseurCourrielEspion
) -> None:
    code = _code(client_auth, fournisseur_courriel_espion)
    r = client_auth.post(
        "/auth/code/verifie",
        json={"email": ADRESSE, "code": code, "telephone": TEL, "nom_complet": "Fatou"},
    )
    jeton = r.cookies[get_settings().cookie_session_nom]
    # Décodé avec la clé DÉRIVÉE, jamais le secret brut (amendement 1, tâche 13) :
    # `poser_cookie` signe avec `cles.deriver(secret_brut, "jeton")`.
    secret_brut = get_settings().jwt_secret.get_secret_value()
    revendications = jetons.decoder(jeton, secret=cles.deriver(secret_brut, "jeton"))
    assert revendications.user_id == r.json()["id"]
    assert revendications.token_version == 0


@pytest.mark.integration
def test_compte_nouveau_sans_telephone(
    client_auth: TestClient, fournisseur_courriel_espion: FournisseurCourrielEspion
) -> None:
    code = _code(client_auth, fournisseur_courriel_espion)
    r = client_auth.post("/auth/code/verifie", json={"email": ADRESSE, "code": code})
    assert r.status_code == 422
    assert r.json()["erreur"] == "inscription_incomplete"


@pytest.mark.integration
def test_le_code_survit_a_une_inscription_incomplete(
    client_auth: TestClient, fournisseur_courriel_espion: FournisseurCourrielEspion
) -> None:
    """Sinon l'utilisateur doit redemander un email pour saisir son nom."""
    code = _code(client_auth, fournisseur_courriel_espion)
    client_auth.post("/auth/code/verifie", json={"email": ADRESSE, "code": code})
    r = client_auth.post(
        "/auth/code/verifie",
        json={"email": ADRESSE, "code": code, "telephone": TEL, "nom_complet": "Fatou"},
    )
    assert r.status_code == 200
    assert len(fournisseur_courriel_espion.envois) == 1  # aucun second email


@pytest.mark.integration
def test_reconnexion_sans_ressaisir(
    client_auth: TestClient, fournisseur_courriel_espion: FournisseurCourrielEspion
) -> None:
    code = _code(client_auth, fournisseur_courriel_espion)
    client_auth.post(
        "/auth/code/verifie",
        json={"email": ADRESSE, "code": code, "telephone": TEL, "nom_complet": "Fatou"},
    )
    code2 = _code(client_auth, fournisseur_courriel_espion)
    r = client_auth.post("/auth/code/verifie", json={"email": ADRESSE, "code": code2})
    assert r.status_code == 200
    assert r.json()["telephone"] == TEL


@pytest.mark.integration
def test_mauvais_code(
    client_auth: TestClient, fournisseur_courriel_espion: FournisseurCourrielEspion
) -> None:
    _code(client_auth, fournisseur_courriel_espion)
    r = client_auth.post(
        "/auth/code/verifie",
        json={"email": ADRESSE, "code": "000000", "telephone": TEL, "nom_complet": "F"},
    )
    assert r.status_code == 400
    assert r.json()["erreur"] == "code_invalide"


@pytest.mark.integration
def test_code_jamais_demande(client_auth: TestClient) -> None:
    r = client_auth.post(
        "/auth/code/verifie",
        json={"email": ADRESSE, "code": "123456", "telephone": TEL, "nom_complet": "F"},
    )
    assert r.status_code == 400
    assert r.json()["erreur"] == "code_expire"


@pytest.mark.integration
def test_code_a_usage_unique(
    client_auth: TestClient, fournisseur_courriel_espion: FournisseurCourrielEspion
) -> None:
    code = _code(client_auth, fournisseur_courriel_espion)
    client_auth.post(
        "/auth/code/verifie",
        json={"email": ADRESSE, "code": code, "telephone": TEL, "nom_complet": "Fatou"},
    )
    r = client_auth.post("/auth/code/verifie", json={"email": ADRESSE, "code": code})
    assert r.status_code == 400
    assert r.json()["erreur"] == "code_expire"


@pytest.mark.integration
def test_plafond_verifications_par_adresse(
    client_auth: TestClient, fournisseur_courriel_espion: FournisseurCourrielEspion
) -> None:
    """Au-delà du plafond par adresse, l'endpoint répond 429 — même avec un
    bon code : le compteur d'essais de `codes.verifier` borne les échecs, pas
    la cadence des tentatives (amendement 2)."""
    plafond = get_settings().auth_verifications_par_heure
    for _ in range(plafond):
        client_auth.post(
            "/auth/code/verifie", json={"email": ADRESSE, "code": "000000", "telephone": TEL}
        )
    r = client_auth.post(
        "/auth/code/verifie", json={"email": ADRESSE, "code": "000000", "telephone": TEL}
    )
    assert r.status_code == 429


@pytest.mark.integration
def test_plafond_verifications_par_ip(
    client_auth: TestClient, fournisseur_courriel_espion: FournisseurCourrielEspion
) -> None:
    """Le plafond par IP protège même quand l'attaquant change d'adresse à
    chaque tentative."""
    plafond = get_settings().auth_verifications_par_ip_heure
    for i in range(plafond):
        client_auth.post(
            "/auth/code/verifie",
            json={"email": f"cible{i}@jobbot-test.sn", "code": "000000", "telephone": TEL},
        )
    r = client_auth.post(
        "/auth/code/verifie",
        json={"email": "derniere@jobbot-test.sn", "code": "000000", "telephone": TEL},
    )
    assert r.status_code == 429


@pytest.mark.integration
def test_verifications_legitimes_sous_le_plafond_passent(
    client_auth: TestClient, fournisseur_courriel_espion: FournisseurCourrielEspion
) -> None:
    """Un utilisateur légitime qui se trompe une ou deux fois avant de réussir
    ne doit jamais être bloqué par ce plafond."""
    code = _code(client_auth, fournisseur_courriel_espion)
    client_auth.post(
        "/auth/code/verifie", json={"email": ADRESSE, "code": "000000", "telephone": TEL}
    )
    r = client_auth.post(
        "/auth/code/verifie",
        json={"email": ADRESSE, "code": code, "telephone": TEL, "nom_complet": "Fatou"},
    )
    assert r.status_code == 200
