"""Protocole d'alerte administrateur (CLAUDE.md §4, §7).

Vit dans `core` pour la même raison que `CacheRedis` (`src/core/cache.py`) :
`core` ne doit dépendre d'aucune implémentation applicative. `src/core/auth/
limites.py` a besoin de signaler un plafond global atteint sans savoir COMMENT
l'alerte part (log, email...) — seule l'implémentation concrète
(`AlerteJournalisee`, dans `src/alerting.py`) en a besoin.
"""

from __future__ import annotations

from typing import Any, Protocol


class AlerteAdmin(Protocol):
    """Canal d'alerte administrateur."""

    async def envoyer(self, evenement: str, **contexte: Any) -> None:
        """Signale un incident d'exploitation à l'administrateur."""
        ...
