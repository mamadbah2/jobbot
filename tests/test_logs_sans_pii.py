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
import structlog.testing
from fastapi.testclient import TestClient

from src.api.app import create_app
from src.api.routers.auth import log as log_du_router_auth
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
        setup_logging("INFO", json_output=True)
        # `setup_logging` active `cache_logger_on_first_use` : tout logger qui
        # émet son premier appel pendant ce test verrait son bind figé pour de
        # bon sur le pipeline ci-dessus, et un `capture_logs()` ultérieur
        # rendrait un journal vide — un faux négatif silencieux, précisément
        # dans la catégorie de test que ce fichier installe (round de
        # correction 1).
        structlog.configure(cache_logger_on_first_use=False)
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


@pytest.mark.integration
def test_exception_non_rattrapee_ne_fuite_rien_et_renvoie_500(
    pipeline_de_logs_reel: io.StringIO,
) -> None:
    """IMPORTANT 7 (revue finale) : une route qui lève une exception non
    rattrapée portant une adresse dans son message doit renvoyer 500, et le
    gestionnaire global (`src/api/app.py`) ne doit journaliser que le nom du
    type de l'exception — jamais l'adresse ni le message brut.
    """
    app = create_app()

    @app.get("/test-exception-non-rattrapee")
    async def _lever_une_exception() -> None:
        raise RuntimeError(f"fuite potentielle vers {ADRESSE}")

    with TestClient(app, raise_server_exceptions=False) as client:
        reponse = client.get("/test-exception-non-rattrapee")

    assert reponse.status_code == 500
    assert reponse.json() == {"erreur": "erreur_interne"}

    rendu = pipeline_de_logs_reel.getvalue()
    assert rendu, "le pipeline réel n'a rien rendu : le test ne prouve rien"
    assert ADRESSE not in rendu
    assert "fuite potentielle" not in rendu
    assert "RuntimeError" in rendu  # le TYPE, seule information journalisée


@pytest.mark.integration
def test_capture_logs_fonctionne_encore_apres_le_pipeline_reel() -> None:
    """Non-régression (round de correction 1) : ce test est marqué
    `integration` — pas parce qu'il touche Postgres ou Redis, mais parce que
    sa seule raison d'être est de s'exécuter dans la même session pytest,
    juste après le test principal (`-m integration` sélectionne les deux,
    dans l'ordre du fichier ; un `pytest -q` sans ce marqueur ne le lancerait
    jamais à la suite du pipeline qu'il vérifie). Sans le
    `structlog.configure(cache_logger_on_first_use=False)` de
    `pipeline_de_logs_reel`, le PREMIER appel d'un logger nommé pendant que
    le test ci-dessus tournait aurait figé son `bind` sur le pipeline JSON
    de ce test — pour de bon, même après la restauration de la configuration
    globale en fin de fixture. Un `capture_logs()` ultérieur sur ce même
    logger rendrait alors un journal **vide** : un faux négatif silencieux,
    précisément la catégorie de test que ce fichier installe.

    Ce test doit s'exécuter APRÈS `test_le_parcours_d_authentification_ne_fuite_rien_dans_les_logs`
    (ordre du fichier, respecté par pytest par défaut) : on réutilise
    l'OBJET module-level `src.api.routers.auth.log` lui-même — celui qui a
    réellement émis `code_demande` et `compte_connecte` pendant le pipeline
    ci-dessus — et non un logger frais obtenu via `get_logger(...)`. Chaque
    appel à `get_logger()`/`structlog.get_logger()` construit une NOUVELLE
    `BoundLoggerLazyProxy` : le cache de `cache_logger_on_first_use` vit sur
    l'instance, pas sur le nom. Un logger fraîchement recréé ici n'aurait
    jamais vu le pipeline pollué et ce test ne prouverait rien.
    """
    with structlog.testing.capture_logs() as journal:
        log_du_router_auth.info("sonde_apres_pipeline")

    assert len(journal) == 1, (
        f"journal vide ou inattendu : {journal!r} — le logger est resté figé "
        "sur le pipeline JSON du test précédent"
    )
    assert journal[0]["event"] == "sonde_apres_pipeline"
