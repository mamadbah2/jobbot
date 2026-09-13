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
    """Canal d'envoi vers une adresse email."""

    async def envoyer_code(self, destinataire: str, code: str) -> None:
        """Transmet le code de vérification à l'adresse indiquée."""
        ...

    async def envoyer_message(self, destinataire: str, sujet: str, corps: str) -> None:
        """Transmet un message quelconque. Sert aux alertes d'exploitation
        (`src/alerting.py`), jamais à un recruteur : le service n'écrit à
        personne d'autre que ses propres utilisateurs et son administrateur
        (CLAUDE.md §2, interdiction n°1, et §7)."""
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
