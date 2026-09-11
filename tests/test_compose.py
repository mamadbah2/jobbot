"""Le fichier compose décrit bien les cinq processus du §4."""

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


def test_le_bot_n_expose_plus_de_port() -> None:
    """Le bot ne sert plus de HTTP depuis le 2026-09-11 (CLAUDE.md §4)."""
    assert "ports" not in SERVICES["bot"]
    assert "healthcheck" not in SERVICES["bot"]


def test_les_cinq_processus_sont_declares() -> None:
    attendus = {"api", "web", "bot", "worker_ingest", "worker_match"}
    assert attendus <= set(SERVICES)


def test_postgres_reste_sur_la_boucle_locale() -> None:
    """Ne jamais exposer la base sur 0.0.0.0 (commentaire du fichier compose)."""
    assert all(str(p).startswith("127.0.0.1:") for p in SERVICES["postgres"]["ports"])
