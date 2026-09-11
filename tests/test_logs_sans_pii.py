"""Aucune donnée personnelle ne sort dans les logs *réellement rendus* (§2).

Les tests existants (`structlog.testing.capture_logs()`, voir p. ex.
`tests/test_api_auth_demande.py`) vérifient les arguments passés au site
d'appel — pas ce qui sortirait vraiment en JSON, puisque `capture_logs()`
vide toute la chaîne de processeurs. Si un jour quelqu'un liait une adresse à
un `contextvar` (motif courant de traçage par requête), ces tests-là
continueraient de passer pendant que l'adresse fuiterait sur chaque ligne.

Celui-ci exerce le VRAI pipeline (`setup_logging(json_output=True)`), capture
la sortie standard pendant un parcours d'authentification complet, et
inspecte ce qui a été rendu.

Lancer avec : RUN_INTEGRATION_TESTS=1 pytest -m integration
"""

from __future__ import annotations

import io
import sys
from collections.abc import Iterator

import pytest
import structlog
from fastapi.testclient import TestClient

from src.config import get_settings
from src.logging_setup import setup_logging
from tests.conftest import FournisseurCourrielEspion, demander_code_verification

ADRESSE = "fatou@jobbot-test.sn"
TEL = "+221771234567"


@pytest.fixture
def pipeline_de_logs_reel() -> Iterator[io.StringIO]:
    """Bascule sur le vrai pipeline structlog (JSON, `PrintLoggerFactory`) le
    temps du test, en capturant sa sortie standard. Restaure la configuration
    de journalisation d'origine en sortie, y compris en cas d'échec du test :
    sinon les tests suivants hériteraient d'une config JSON pointant vers un
    buffer fermé.
    """
    config_avant = structlog.get_config()
    stdout_avant = sys.stdout
    tampon = io.StringIO()
    sys.stdout = tampon
    try:
        # `setup_logging` lit `sys.stdout` à l'appel (`PrintLoggerFactory`,
        # `logging.basicConfig`) : il faut donc rediriger AVANT de l'appeler,
        # pas nous contenter de capturer après coup.
        setup_logging(json_output=True)
        yield tampon
    finally:
        sys.stdout = stdout_avant
        structlog.configure(**config_avant)


@pytest.mark.integration
def test_le_parcours_d_authentification_ne_fuite_rien_dans_les_logs(
    client_auth: TestClient,
    fournisseur_courriel_espion: FournisseurCourrielEspion,
    pipeline_de_logs_reel: io.StringIO,
) -> None:
    """Demande de code, vérification, `/moi`, déconnexion — la sortie JSON
    rendue ne doit contenir ni l'adresse, ni le téléphone, ni le code, ni le
    jeton de session (§2, interdiction n°2 ; contraintes-globales l.15-16).

    `client_auth` surcharge déjà le fournisseur de courriel par l'espion : le
    fournisseur `console` (seule exception documentée, `src/courriel/console.py`)
    n'est donc jamais sollicité ici.
    """
    code = demander_code_verification(client_auth, fournisseur_courriel_espion, ADRESSE)

    reponse = client_auth.post(
        "/auth/code/verifie",
        json={
            "email": ADRESSE,
            "code": code,
            "telephone": TEL,
            "nom_complet": "Fatou Diop",
        },
    )
    assert reponse.status_code == 200
    jeton = reponse.cookies[get_settings().cookie_session_nom]

    assert client_auth.get("/moi").status_code == 200
    assert client_auth.post("/auth/deconnexion").status_code == 204

    rendu = pipeline_de_logs_reel.getvalue()
    assert rendu, "le pipeline réel n'a rien rendu : le test ne prouve rien"

    assert ADRESSE not in rendu
    assert TEL not in rendu
    assert TEL.removeprefix("+") not in rendu  # forme sans l'indicatif
    assert TEL.removeprefix("+221") not in rendu  # forme locale à 9 chiffres
    assert code not in rendu
    assert jeton not in rendu
