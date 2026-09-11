"""Le strict minimum de l'API Redis dont `core` a besoin.

Un Protocol plutôt qu'un client concret : les tests unitaires n'ont pas le droit
de toucher au réseau (`tests/conftest.py`), et `core` ne doit dépendre d'aucune
bibliothèque cliente.
"""

from __future__ import annotations

from typing import Any, Protocol


class CacheRedis(Protocol):
    async def get(self, name: str) -> Any: ...
    async def set(
        self, name: str, value: str, *, ex: int | None = None, nx: bool = False
    ) -> Any: ...
    async def delete(self, *names: str) -> Any: ...
    async def incr(self, name: str) -> int: ...
    async def expire(self, name: str, time: int) -> Any: ...
