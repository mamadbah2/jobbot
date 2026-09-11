"""Interface d'envoi et fabrique (spec Phase 2 §7).

Même forme que `src/alerting.py` : le métier ne connaît que l'interface, et le
fournisseur réel se branche sans toucher à un seul appelant.

Aucun fournisseur réel n'existe en Phase 2 : SPF, DKIM et DMARC exigent un
domaine possédé, encore à acheter (CLAUDE.md §14.1).
"""

from __future__ import annotations

from typing import Protocol

from src.config import Settings
from src.courriel.console import CourrielConsole


class FournisseurCourriel(Protocol):
    """Canal d'envoi du code de vérification."""

    async def envoyer_code(self, destinataire: str, code: str) -> None:
        """Transmet le code à l'adresse indiquée."""
        ...


def construire_fournisseur(settings: Settings) -> FournisseurCourriel:
    """Fournisseur à utiliser, selon la configuration."""
    if settings.fournisseur_courriel == "console":
        return CourrielConsole()
    # Pas de repli silencieux : une faute de frappe dans la variable
    # d'environnement enverrait les codes dans les logs en production.
    raise ValueError(
        f"FOURNISSEUR_COURRIEL inconnu : {settings.fournisseur_courriel!r}. "
        "Valeurs acceptées : console."
    )
