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
def _sans_garde_fous_demande(monkeypatch: pytest.MonkeyPatch) -> None:
    """Plusieurs tests de ce module (reconnexion, plafond de vérification par
    adresse et par IP) enchaînent plusieurs `/auth/code/demande` pour la même
    adresse dans un même test. Les garde-fous de cet endpoint (§10, cooldown
    et quotas d'ENVOI, distincts du plafond de VÉRIFICATION testé ici)
    n'ont pas leur place dans ces scénarios.
    """
    monkeypatch.setenv("AUTH_COOLDOWN_SECONDES", "0")
    monkeypatch.setenv("AUTH_ENVOIS_PAR_HEURE", "1000")
    monkeypatch.setenv("AUTH_ENVOIS_PAR_JOUR", "1000")
    monkeypatch.setenv("AUTH_ENVOIS_PAR_IP_HEURE", "1000")
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
def test_le_code_survit_a_un_numero_invalide(
    client_auth: TestClient, fournisseur_courriel_espion: FournisseurCourrielEspion
) -> None:
    """Important 3 (revue finale) : une faute de frappe dans le numéro est
    l'erreur la plus banale du parcours (§11). Elle ne doit pas obliger
    l'utilisateur à redemander un email, comme `InscriptionIncomplete`."""
    code = _code(client_auth, fournisseur_courriel_espion)
    r = client_auth.post(
        "/auth/code/verifie",
        json={"email": ADRESSE, "code": code, "telephone": "pas un numero",
              "nom_complet": "Fatou Diop"},
    )
    assert r.status_code == 422
    assert r.json()["erreur"] == "numero_invalide"
    # Le même code, corrigé, doit encore fonctionner.
    r = client_auth.post(
        "/auth/code/verifie",
        json={"email": ADRESSE, "code": code, "telephone": TEL, "nom_complet": "Fatou Diop"},
    )
    assert r.status_code == 200
    assert len(fournisseur_courriel_espion.envois) == 1  # aucun second email


@pytest.mark.integration
def test_le_code_survit_a_un_telephone_deja_utilise(
    client_auth: TestClient, fournisseur_courriel_espion: FournisseurCourrielEspion
) -> None:
    """Idem pour `TelephoneDejaUtilise` : deux comptes ne partagent jamais un
    numéro (§5), mais la victime de cette collision doit pouvoir corriger
    sans redemander un email."""
    autre_adresse = "autre@jobbot-test.sn"
    autre_code = _code(client_auth, fournisseur_courriel_espion, autre_adresse)
    r = client_auth.post(
        "/auth/code/verifie",
        json={"email": autre_adresse, "code": autre_code, "telephone": TEL,
              "nom_complet": "Premier Compte"},
    )
    assert r.status_code == 200

    code = _code(client_auth, fournisseur_courriel_espion)
    r = client_auth.post(
        "/auth/code/verifie",
        json={"email": ADRESSE, "code": code, "telephone": TEL, "nom_complet": "Fatou Diop"},
    )
    assert r.status_code == 409
    assert r.json()["erreur"] == "telephone_deja_utilise"
    # Le même code, avec un numéro différent, doit encore fonctionner.
    r = client_auth.post(
        "/auth/code/verifie",
        json={"email": ADRESSE, "code": code, "telephone": "+221781234567",
              "nom_complet": "Fatou Diop"},
    )
    assert r.status_code == 200


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
    """Au-delà du plafond par adresse, l'endpoint répond 429 — mais seulement
    quand la tentative porte sur un code qui existe vraiment et qu'il est
    faux (round de correction 1) : chaque itération redépose un vrai code
    puis le rate avec un mauvais, pour que chaque tentative lève bien
    `CodeInvalide` (la seule chose qui consomme ce plafond), pas `CodeExpire`.
    """
    plafond = get_settings().auth_verifications_par_heure
    for _ in range(plafond):
        _code(client_auth, fournisseur_courriel_espion)
        r = client_auth.post(
            "/auth/code/verifie", json={"email": ADRESSE, "code": "000000", "telephone": TEL}
        )
        assert r.json()["erreur"] == "code_invalide"
    _code(client_auth, fournisseur_courriel_espion)
    r = client_auth.post(
        "/auth/code/verifie", json={"email": ADRESSE, "code": "000000", "telephone": TEL}
    )
    assert r.status_code == 429


@pytest.mark.integration
def test_code_expire_ne_consomme_pas_le_plafond_par_adresse(
    client_auth: TestClient, fournisseur_courriel_espion: FournisseurCourrielEspion
) -> None:
    """Preuve du correctif (round de correction 1) : un tiers qui connaît
    l'adresse d'une victime mais n'a jamais reçu de code ne doit rien pouvoir
    lui consommer. Sinon connaître un email suffirait à bloquer les
    connexions de son propriétaire pendant une heure."""
    plafond = get_settings().auth_verifications_par_heure
    for _ in range(plafond):
        r = client_auth.post(
            "/auth/code/verifie", json={"email": ADRESSE, "code": "000000", "telephone": TEL}
        )
        assert r.status_code == 400
        assert r.json()["erreur"] == "code_expire"
    # La victime peut toujours vérifier son propre code après coup : son
    # quota par adresse n'a pas été entamé par les tentatives d'un tiers.
    code = _code(client_auth, fournisseur_courriel_espion)
    r = client_auth.post(
        "/auth/code/verifie",
        json={"email": ADRESSE, "code": code, "telephone": TEL, "nom_complet": "Fatou"},
    )
    assert r.status_code == 200


@pytest.mark.integration
def test_plafond_verifications_par_ip(
    client_auth: TestClient, fournisseur_courriel_espion: FournisseurCourrielEspion
) -> None:
    """Le plafond par IP protège même quand l'attaquant change d'adresse à
    chaque tentative — et même sans code en cours pour aucune d'elles,
    puisqu'il est indexé sur la seule IP (round de correction 1)."""
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
