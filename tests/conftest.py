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


class FauxCache:
    """Redis en mémoire, réduit à ce dont `core` a besoin.

    Les tests unitaires ne touchent ni le réseau ni la base : un vrai Redis
    en ferait des tests d'intégration.
    """

    def __init__(self) -> None:
        self.valeurs: dict[str, str] = {}
        self.ttl: dict[str, int] = {}

    async def get(self, name: str) -> str | None:
        return self.valeurs.get(name)

    async def set(
        self, name: str, value: str, *, ex: int | None = None, nx: bool = False
    ) -> bool:
        if nx and name in self.valeurs:
            return False
        self.valeurs[name] = value
        if ex is not None:
            self.ttl[name] = ex
        return True

    async def delete(self, *names: str) -> int:
        efface = 0
        for name in names:
            efface += 1 if self.valeurs.pop(name, None) is not None else 0
            self.ttl.pop(name, None)
        return efface

    async def incr(self, name: str) -> int:
        valeur = int(self.valeurs.get(name, "0")) + 1
        self.valeurs[name] = str(valeur)
        return valeur

    async def expire(self, name: str, time: int, *, nx: bool = False) -> bool:
        if name not in self.valeurs:
            return False
        if nx and name in self.ttl:
            return False
        self.ttl[name] = time
        return True

    async def expirer_maintenant(self, *names: str) -> None:
        """Helper de test : simule l'expiration du TTL, sans attendre."""
        await self.delete(*names)


@pytest.fixture
def faux_cache() -> FauxCache:
    return FauxCache()
