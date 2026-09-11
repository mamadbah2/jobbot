"""Fournisseur de développement : le code part dans les logs.

ATTENTION — c'est le SEUL endroit du projet où un code de vérification a le
droit d'être journalisé (CLAUDE.md §2, interdiction n°2). Ne jamais copier ce
motif ailleurs, et ne jamais activer ce fournisseur en production : quiconque
lit les logs peut ouvrir n'importe quelle session.
"""

from __future__ import annotations

from src.logging_setup import get_logger

log = get_logger(__name__)


class CourrielConsole:
    """Écrit le code au lieu de l'envoyer."""

    async def envoyer_code(self, destinataire: str, code: str) -> None:
        log.warning(
            "courriel_non_envoye_mode_console",
            destinataire=destinataire,
            code=code,
            rappel="Aucun email n'a été envoyé. Voir CLAUDE.md §14.1 (nom de domaine).",
        )
