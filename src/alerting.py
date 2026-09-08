"""Alertes administrateur (CLAUDE.md §7, §12 Phase 6).

« Ne jamais échouer en silence » : un scraper cassé, une source bloquée ou un
changement de structure doivent sortir du fichier de logs et arriver à
quelqu'un. Le canal prévu est Telegram, mais `ADMIN_TELEGRAM_ID` n'est pas
encore fourni (§14) : l'implémentation par défaut journalise en ERROR et dit
explicitement qu'aucun destinataire n'est configuré.

L'envoi Telegram viendra derrière la même interface, sans toucher aux
appelants : le worker d'ingestion ne connaît que `AlerteAdmin`.
"""

from __future__ import annotations

from typing import Any, Protocol

from src.config import Settings
from src.logging_setup import get_logger

log = get_logger(__name__)


class AlerteAdmin(Protocol):
    """Canal d'alerte administrateur."""

    async def envoyer(self, evenement: str, **contexte: Any) -> None:
        """Signale un incident d'exploitation à l'administrateur."""
        ...


class AlerteJournalisee:
    """Alerte écrite dans les logs en niveau ERROR.

    Sert de repli permanent : même quand l'envoi Telegram existera, une
    alerte doit rester traçable dans les logs du VPS.
    """

    def __init__(self, admin_telegram_id: int) -> None:
        self.admin_telegram_id = admin_telegram_id

    async def envoyer(self, evenement: str, **contexte: Any) -> None:
        destinataire = str(self.admin_telegram_id) if self.admin_telegram_id else "absent"
        log.error(
            "alerte_admin",
            alerte=evenement,
            destinataire=destinataire,
            # Sans identifiant, personne n'est prévenu : le dire dans l'événement
            # évite de croire l'alerte transmise (§14, point encore ouvert).
            canal="log" if self.admin_telegram_id else "log_uniquement_admin_non_configure",
            **contexte,
        )


def construire_alerte(settings: Settings) -> AlerteAdmin:
    """Canal d'alerte à utiliser, selon la configuration."""
    return AlerteJournalisee(admin_telegram_id=settings.admin_telegram_id)
