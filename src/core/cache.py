"""Le strict minimum de l'API Redis dont le projet a besoin.

Un Protocol plutôt qu'un client concret : les tests unitaires n'ont pas le droit
de toucher au réseau (`tests/conftest.py`), et `core` ne doit dépendre d'aucune
bibliothèque cliente.

**Un seul Protocol pour tout le dépôt.** `src/ingest/fraicheur.py` en portait un
second, homonyme et de forme différente : deux types du même nom dans la même
couche, que mypy refusait d'unifier, d'où un `cast` dans `routers/offres.py`
pour recoller les deux moitiés.

Méthodes déclarées **non-`async`, rendant un `Awaitable`**, et non `async def`.
La nuance décide de la compatibilité avec `redis.asyncio` : ses stubs déclarent
`get`/`set`/`delete` en retour `T | Awaitable[T]` (le client synchrone et
l'asynchrone partagent la même classe de base). Un `async def` dans le Protocol
exigerait un `Coroutine`, que `Awaitable` ne satisfait pas, et le vrai client
Redis échouerait au typage. Sous cette forme, il passe sans `cast`. Un
`async def` d'implémentation reste accepté : il rend une `Coroutine`, qui *est*
un `Awaitable`.
"""

from __future__ import annotations

from collections.abc import Awaitable
from typing import Any, Protocol


class CacheRedis(Protocol):
    def get(self, name: str) -> Awaitable[Any]: ...
    def set(
        self, name: str, value: str, *, ex: int | None = None, nx: bool = False
    ) -> Awaitable[Any]: ...
    def delete(self, *names: str) -> Awaitable[Any]: ...
    def incr(self, name: str) -> Awaitable[int]: ...
    def expire(self, name: str, time: int, *, nx: bool = False) -> Awaitable[Any]: ...
