"""Fixtures communes. Aucun test unitaire ne doit toucher au réseau ni à la base.

Les fixtures qui touchent Postgres (`base_utilisateurs_test`, `client_auth`) sont
donc **paresseuses** : les imports ci-dessous ne font qu'importer des modules,
ils n'ouvrent aucune connexion. Seul un test qui les déclare explicitement en
paramètre déclenche `create_async_engine`/`TestClient` — un `pytest -q` sans
`-m integration` ne les instancie jamais.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator, Iterator
from typing import Any

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from src.api import deps
from src.api.app import create_app
from src.config import Settings, get_settings
from src.db.models import User

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


class FournisseurCourrielEspion:
    """Fournisseur de courriel factice : capture les codes envoyés, n'envoie
    jamais rien réellement. Partagé par les tests d'authentification qui
    vérifient le cycle complet demande -> vérification (tâches 13, 14, ...).
    """

    def __init__(self) -> None:
        self.envois: list[tuple[str, str]] = []
        self.messages: list[tuple[str, str, str]] = []

    async def envoyer_code(self, destinataire: str, code: str) -> None:
        self.envois.append((destinataire, code))

    async def envoyer_message(self, destinataire: str, sujet: str, corps: str) -> None:
        self.messages.append((destinataire, sujet, corps))


@pytest.fixture
def fournisseur_courriel_espion() -> FournisseurCourrielEspion:
    return FournisseurCourrielEspion()


@pytest_asyncio.fixture
async def base_utilisateurs_test(
    postgres_url: str,
) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    """Fabrique de sessions vers la vraie base, purgée des comptes de test
    (`%@jobbot-test.sn`) avant et après. N'ouvre une connexion que lorsqu'un
    test d'intégration la déclare en paramètre — jamais au chargement de ce
    fichier ni pour les tests unitaires.

    `poolclass=NullPool` : ce fixture s'exécute sur la boucle asyncio de
    pytest-asyncio, mais `client_auth` réutilise la même fabrique depuis la
    boucle propre au `TestClient` (un thread séparé). Avec un pool qui
    retient les connexions, la connexion asyncpg ouverte ici pour la purge
    resurgirait plus tard dans l'autre boucle et ferait planter la requête
    (`RuntimeError: Future attached to a different loop`). Sans pool, chaque
    checkout ouvre une connexion fraîche sur la boucle courante.
    """
    moteur = create_async_engine(postgres_url, poolclass=NullPool)
    fabrique = async_sessionmaker(moteur, expire_on_commit=False)
    async with fabrique() as s:
        await s.execute(delete(User).where(User.email.like("%@jobbot-test.sn")))
        await s.commit()
    yield fabrique
    async with fabrique() as s:
        await s.execute(delete(User).where(User.email.like("%@jobbot-test.sn")))
        await s.commit()
    await moteur.dispose()


@pytest.fixture
def client_auth(
    fournisseur_courriel_espion: FournisseurCourrielEspion,
    faux_cache: FauxCache,
    base_utilisateurs_test: async_sessionmaker[AsyncSession],
) -> Iterator[TestClient]:
    """Client HTTP branché sur la vraie base et un fournisseur de courriel
    espionné : sert les tests d'intégration de `/auth/code/demande` et
    `/auth/code/verifie` (tâches 13, 14, ...).
    """
    from src.api.routers import auth

    app = create_app()

    async def _cache() -> Any:
        yield faux_cache

    async def _session() -> Any:
        # Reproduit exactement `src/db/session.py::session_scope` : sans le
        # rollback sur exception, les tests d'intégration tourneraient avec
        # une sémantique différente de la production, précisément sur les
        # chemins d'erreur qui comptent (round de correction finale).
        async with base_utilisateurs_test() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[deps.cache_redis] = _cache
    app.dependency_overrides[deps.session_db] = _session
    app.dependency_overrides[auth.fournisseur] = lambda: fournisseur_courriel_espion
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


def demander_code_verification(
    client: TestClient, espion: FournisseurCourrielEspion, adresse: str
) -> str:
    """Déclenche `/auth/code/demande` et renvoie le code intercepté par l'espion."""
    client.post("/auth/code/demande", json={"email": adresse})
    return espion.envois[-1][1]
