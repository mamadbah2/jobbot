"""Le fichier compose décrit bien les processus du §4."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

yaml = pytest.importorskip("yaml")

COMPOSE: dict[str, Any] = yaml.safe_load(Path("docker-compose.yml").read_text(encoding="utf-8"))
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
