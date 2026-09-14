"""Le fichier compose décrit bien les processus du §4."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest

from src.config import Settings

yaml = pytest.importorskip("yaml")

CHEMIN_COMPOSE = Path("docker-compose.yml")
TEXTE_COMPOSE = CHEMIN_COMPOSE.read_text(encoding="utf-8")
COMPOSE: dict[str, Any] = yaml.safe_load(TEXTE_COMPOSE)
SERVICES: dict[str, Any] = COMPOSE["services"]


def test_le_service_api_existe() -> None:
    assert SERVICES["api"]["command"] == ["python", "-m", "src.api.main"]


def test_l_api_expose_le_port_http() -> None:
    assert any("HTTP_PORT" in str(p) for p in SERVICES["api"]["ports"])


def test_l_api_porte_le_healthcheck() -> None:
    assert "health" in str(SERVICES["api"]["healthcheck"]["test"])


def test_le_bot_n_existe_plus() -> None:
    """Le bot a été supprimé le 2026-09-12 : il n'est plus un client du produit."""
    assert "bot" not in SERVICES


def test_les_quatre_processus_sont_declares() -> None:
    attendus = {"api", "web", "worker_ingest", "worker_match"}
    assert attendus <= set(SERVICES)


def test_postgres_reste_sur_la_boucle_locale() -> None:
    """Ne jamais exposer la base sur 0.0.0.0 (commentaire du fichier compose)."""
    assert all(str(p).startswith("127.0.0.1:") for p in SERVICES["postgres"]["ports"])


def test_les_services_applicatifs_partagent_la_meme_politique_de_dependance() -> None:
    """api, worker_ingest et worker_match doivent dépendre des mêmes services,
    dans les mêmes conditions — factorisé via l'ancre `x-depends-app` pour éviter
    qu'une future modification n'en oublie un.
    """
    services = ("api", "worker_ingest", "worker_match")
    politiques = [SERVICES[nom]["depends_on"] for nom in services]
    assert all(p == politiques[0] for p in politiques)
    assert politiques[0] == {
        "postgres": {"condition": "service_healthy"},
        "redis": {"condition": "service_healthy"},
        "migrate": {"condition": "service_completed_successfully"},
    }


def test_l_api_reste_sur_la_boucle_locale() -> None:
    """Si l'API est joignable de l'extérieur, on contourne Next et on se forge
    le X-Forwarded-For de son choix : les plafonds par IP ne valent plus rien
    (spec du client web §6)."""
    assert all(str(p).startswith("127.0.0.1:") for p in SERVICES["api"]["ports"])


def test_le_web_n_est_plus_derriere_un_profil() -> None:
    """Le service était déclaré en prévision ; il devient réel."""
    assert "profiles" not in SERVICES["web"]


def test_le_web_est_publie_sur_l_hote() -> None:
    assert any("WEB_HOST_PORT" in str(p) for p in SERVICES["web"]["ports"])


def test_le_web_attend_que_l_api_soit_saine() -> None:
    assert SERVICES["web"]["depends_on"]["api"] == {"condition": "service_healthy"}


# ─── Un réglage documenté doit atteindre un process ──────────────────────────
#
# Le trou par lequel est passée la confiance au proxy : `.env.example` la
# documentait, mais rien ne la transmettait au client web. Les tests d'alors
# vérifiaient les ports et les profils, jamais qu'un réglage arrive à
# destination.
#
# Une clé de `.env.example` est « transmise » si l'une de ces trois voies
# existe. La première est la plus large, mais elle ne couvre QUE les services
# Python : `web` n'a pas d'`env_file` et ne reçoit que ce qu'on lui nomme.
#
#   1. un champ correspondant dans `Settings` (src/config.py) — le réglage
#      atteint alors api, migrate, worker_ingest et worker_match, qui portent
#      tous `env_file: .env` ;
#   2. une entrée explicite dans le bloc `environment:` d'un service ;
#   3. une interpolation `${CLE}` dans docker-compose.yml — la clé façonne
#      alors le déploiement lui-même (un port publié, par exemple) sans avoir
#      à entrer dans un conteneur.

# Exemptions, avec leur motif. Une exemption sans motif ne survit pas six mois.
CLES_EXEMPTES: dict[str, str] = {
    # Rien à exempter aujourd'hui. Les clés que seuls postgres et redis
    # consomment (POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_DB) n'ont pas
    # besoin d'exemption : elles sont nommées dans le bloc `environment:` de
    # postgres ET portées par Settings, donc couvertes par les voies 1 et 2.
}


def _cles_env_example() -> list[str]:
    lignes = Path(".env.example").read_text(encoding="utf-8").splitlines()
    return [
        ligne.split("=", 1)[0].strip()
        for ligne in lignes
        if "=" in ligne and not ligne.lstrip().startswith("#")
    ]


def _cles_des_blocs_environment() -> set[str]:
    return {
        cle for service in SERVICES.values() for cle in (service.get("environment") or {})
    }


def _cles_interpolees() -> set[str]:
    """`${CLE}` et `${CLE:-defaut}`, quelle que soit la forme."""
    return set(re.findall(r"\$\{([A-Z0-9_]+)", TEXTE_COMPOSE))


def test_chaque_cle_documentee_atteint_un_process() -> None:
    champs_settings = {nom.upper() for nom in Settings.model_fields}
    explicites = _cles_des_blocs_environment()
    interpolees = _cles_interpolees()

    orphelines = [
        cle
        for cle in _cles_env_example()
        if cle not in CLES_EXEMPTES
        and cle not in champs_settings
        and cle not in explicites
        and cle not in interpolees
    ]
    assert not orphelines, (
        "ces clés de .env.example ne parviennent à aucun process : "
        f"{orphelines}. Ajoutez-les au bloc `environment:` du service qui les "
        "consomme, ou à `Settings` (src/config.py), ou exemptez-les dans "
        "CLES_EXEMPTES en disant pourquoi."
    )


def test_le_web_recoit_tout_ce_qu_il_lit_dans_l_environnement() -> None:
    """La voie 1 ne protège pas `web` : sans `env_file`, il ne reçoit que ce
    qui est nommé. Un `process.env.X` non transmis ne casse rien bruyamment —
    il retombe sur sa valeur par défaut, ce qui est le pire mode de
    défaillance : `WEB_DERRIERE_PROXY` absent vaut `false`, donc plus aucun
    X-Forwarded-For relayé, et pas le moindre message.
    """
    lus: set[str] = set()
    for source in Path("web/app").rglob("*.ts*"):
        lus |= set(
            re.findall(r"process\.env\.([A-Z0-9_]+)", source.read_text(encoding="utf-8"))
        )
    assert lus, "aucun process.env lu dans web/app : le test ne prouve plus rien"

    fournies = set(SERVICES["web"].get("environment") or {})
    manquantes = sorted(lus - fournies)
    assert not manquantes, (
        f"le service `web` lit {manquantes} sans que docker-compose.yml ne les "
        "lui transmette : ajoutez-les à son bloc `environment:`."
    )


def test_le_web_ne_fait_pas_confiance_au_proxy_par_defaut() -> None:
    """Fermé par défaut. Rien ne se tient devant `web` : à `true`, le
    X-Forwarded-For relayé serait celui que le client a écrit lui-même, et les
    plafonds par IP deviendraient contournables en faisant tourner la valeur.
    """
    assert (
        SERVICES["web"]["environment"]["WEB_DERRIERE_PROXY"]
        == "${WEB_DERRIERE_PROXY:-false}"
    )
