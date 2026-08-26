"""Fixtures communes. Aucun test unitaire ne doit toucher au réseau ni à la base."""

from __future__ import annotations

import os
from collections.abc import Iterator

import pytest

from src.config import Settings, get_settings

_ENV_MINIMAL = {
    "TELEGRAM_BOT_TOKEN": "123456:TOKEN_DE_TEST",
    "POSTGRES_HOST": "localhost",
    "POSTGRES_PASSWORD": "motdepasse_test",
}


@pytest.fixture(autouse=True)
def env_minimal(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Environnement minimal + cache de config vidé entre chaque test."""
    # Un .env présent sur la machine du dev ne doit pas influencer les tests.
    monkeypatch.setitem(Settings.model_config, "env_file", None)
    for cle, valeur in _ENV_MINIMAL.items():
        monkeypatch.setenv(cle, valeur)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def postgres_url() -> str:
    """DSN de la base d'intégration (tests marqués `integration`)."""
    return os.environ.get(
        "TEST_DATABASE_URL",
        "postgresql+asyncpg://jobbot:jobbot_dev_password@localhost:55432/jobbot",
    )
