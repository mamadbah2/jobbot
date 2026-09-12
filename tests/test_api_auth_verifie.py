"""POST /auth/code/verifie (spec Phase 2 §8).

Depuis le 2026-09-12 (tâche 18), cet endpoint ne prend plus de téléphone :
le code à 6 chiffres ne prouve que la possession de l'adresse email, jamais
celle d'un numéro saisi au clavier. `telephone` a disparu de
`VerificationCode`. Depuis la migration 0005 (retrait de Telegram, même
date), `Utilisateur` n'expose plus du tout de champ `telephone` : la réponse
se limite à `id`, `email`, `nom_complet`, `etat`.

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
        json={"email": ADRESSE, "code": code, "nom_complet": "Fatou Diop"},
    )
    assert r.status_code == 200
    corps = r.json()
    assert corps["email"] == ADRESSE
    assert set(corps) == {"id", "email", "nom_complet", "etat"}
    assert get_settings().cookie_session_nom in r.cookies


@pytest.mark.integration
def test_telephone_dans_le_corps_est_ignore(
    client_auth: TestClient, fournisseur_courriel_espion: FournisseurCourrielEspion
) -> None:
    """La propriété qui remplace l'ancien couple numero_invalide/telephone_deja_
    utilise à cet endpoint : `VerificationCode` n'a plus de champ `telephone`,
    donc un client qui en envoie un quand même (ancien client web pas encore
    mis à jour, requête forgée) ne pose AUCUN numéro — pydantic l'ignore
    silencieusement, il n'atteint jamais `connecter_ou_inscrire`."""
    code = _code(client_auth, fournisseur_courriel_espion)
    r = client_auth.post(
        "/auth/code/verifie",
        json={
            "email": ADRESSE,
            "code": code,
            "telephone": "pas un numero du tout",
            "nom_complet": "Fatou Diop",
        },
    )
    assert r.status_code == 200


@pytest.mark.integration
def test_le_cookie_est_httponly(
    client_auth: TestClient, fournisseur_courriel_espion: FournisseurCourrielEspion
) -> None:
    """Un cookie lisible en JS est volable par n'importe quelle faille XSS."""
    code = _code(client_auth, fournisseur_courriel_espion)
    r = client_auth.post(
        "/auth/code/verifie",
        json={"email": ADRESSE, "code": code, "nom_complet": "Fatou"},
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
        json={"email": ADRESSE, "code": code, "nom_complet": "Fatou"},
    )
    jeton = r.cookies[get_settings().cookie_session_nom]
    # Décodé avec la clé DÉRIVÉE, jamais le secret brut (amendement 1, tâche 13) :
    # `poser_cookie` signe avec `cles.deriver(secret_brut, "jeton")`.
    secret_brut = get_settings().jwt_secret.get_secret_value()
    revendications = jetons.decoder(jeton, secret=cles.deriver(secret_brut, "jeton"))
    assert revendications.user_id == r.json()["id"]
    assert revendications.token_version == 0


@pytest.mark.integration
def test_compte_nouveau_sans_nom(
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
        json={"email": ADRESSE, "code": code, "nom_complet": "Fatou"},
    )
    assert r.status_code == 200
    assert len(fournisseur_courriel_espion.envois) == 1  # aucun second email


@pytest.mark.integration
def test_deux_inscriptions_independantes_sans_telephone(
    client_auth: TestClient, fournisseur_courriel_espion: FournisseurCourrielEspion
) -> None:
    """La propriété qui remplace l'ancien `test_le_code_survit_a_un_telephone_
    deja_utilise` : deux comptes différents peuvent s'inscrire l'un après
    l'autre sans jamais entrer en collision sur un numéro, tout simplement
    parce qu'aucun numéro n'entre plus nulle part depuis la migration 0005
    — `users` n'a plus de colonne `phone` du tout."""
    autre_adresse = "autre@jobbot-test.sn"
    autre_code = _code(client_auth, fournisseur_courriel_espion, autre_adresse)
    r1 = client_auth.post(
        "/auth/code/verifie",
        json={"email": autre_adresse, "code": autre_code, "nom_complet": "Premier Compte"},
    )
    assert r1.status_code == 200

    code = _code(client_auth, fournisseur_courriel_espion)
    r2 = client_auth.post(
        "/auth/code/verifie",
        json={"email": ADRESSE, "code": code, "nom_complet": "Fatou Diop"},
    )
    assert r2.status_code == 200
    assert r2.json()["id"] != r1.json()["id"]


@pytest.mark.integration
def test_reconnexion_sans_ressaisir_le_nom(
    client_auth: TestClient, fournisseur_courriel_espion: FournisseurCourrielEspion
) -> None:
    code = _code(client_auth, fournisseur_courriel_espion)
    client_auth.post(
        "/auth/code/verifie",
        json={"email": ADRESSE, "code": code, "nom_complet": "Fatou"},
    )
    code2 = _code(client_auth, fournisseur_courriel_espion)
    r = client_auth.post("/auth/code/verifie", json={"email": ADRESSE, "code": code2})
    assert r.status_code == 200


@pytest.mark.integration
def test_mauvais_code(
    client_auth: TestClient, fournisseur_courriel_espion: FournisseurCourrielEspion
) -> None:
    _code(client_auth, fournisseur_courriel_espion)
    r = client_auth.post(
        "/auth/code/verifie",
        json={"email": ADRESSE, "code": "000000", "nom_complet": "F"},
    )
    assert r.status_code == 400
    assert r.json()["erreur"] == "code_invalide"


@pytest.mark.integration
def test_code_jamais_demande(client_auth: TestClient) -> None:
    r = client_auth.post(
        "/auth/code/verifie",
        json={"email": ADRESSE, "code": "123456", "nom_complet": "F"},
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
        json={"email": ADRESSE, "code": code, "nom_complet": "Fatou"},
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
        r = client_auth.post("/auth/code/verifie", json={"email": ADRESSE, "code": "000000"})
        assert r.json()["erreur"] == "code_invalide"
    _code(client_auth, fournisseur_courriel_espion)
    r = client_auth.post("/auth/code/verifie", json={"email": ADRESSE, "code": "000000"})
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
        r = client_auth.post("/auth/code/verifie", json={"email": ADRESSE, "code": "000000"})
        assert r.status_code == 400
        assert r.json()["erreur"] == "code_expire"
    # La victime peut toujours vérifier son propre code après coup : son
    # quota par adresse n'a pas été entamé par les tentatives d'un tiers.
    code = _code(client_auth, fournisseur_courriel_espion)
    r = client_auth.post(
        "/auth/code/verifie",
        json={"email": ADRESSE, "code": code, "nom_complet": "Fatou"},
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
            json={"email": f"cible{i}@jobbot-test.sn", "code": "000000"},
        )
    r = client_auth.post(
        "/auth/code/verifie",
        json={"email": "derniere@jobbot-test.sn", "code": "000000"},
    )
    assert r.status_code == 429


@pytest.mark.integration
def test_verifications_legitimes_sous_le_plafond_passent(
    client_auth: TestClient, fournisseur_courriel_espion: FournisseurCourrielEspion
) -> None:
    """Un utilisateur légitime qui se trompe une ou deux fois avant de réussir
    ne doit jamais être bloqué par ce plafond."""
    code = _code(client_auth, fournisseur_courriel_espion)
    client_auth.post("/auth/code/verifie", json={"email": ADRESSE, "code": "000000"})
    r = client_auth.post(
        "/auth/code/verifie",
        json={"email": ADRESSE, "code": code, "nom_complet": "Fatou"},
    )
    assert r.status_code == 200
