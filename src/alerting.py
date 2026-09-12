"""Alertes administrateur (CLAUDE.md §7, §12 Phase 8).

« Ne jamais échouer en silence » : un scraper cassé, une source bloquée ou un
changement de structure doivent sortir du fichier de logs et arriver à
quelqu'un.

Le canal était Telegram jusqu'au 2026-09-12. Il passe à l'email, derrière le
même protocole `AlerteAdmin` : ni `src/core/auth/limites.py` ni le worker
d'ingestion ne changent d'une ligne. Le bac à sable d'un fournisseur
transactionnel sait envoyer vers l'adresse vérifiée du propriétaire du compte
sans domaine possédé, donc ce canal est exploitable avant que le §14.1 soit
tranché — contrairement aux emails vers de vrais utilisateurs.

Sans `ADMIN_COURRIEL`, on retombe sur le log : c'est un état dégradé mais
fonctionnel, et l'événement le dit explicitement pour qu'on ne croie pas
l'alerte transmise.
"""

from __future__ import annotations

from typing import Any

from src.config import Settings
from src.core.alerte import AlerteAdmin
from src.courriel.provider import FournisseurCourriel, construire_fournisseur
from src.logging_setup import get_logger

log = get_logger(__name__)

__all__ = ["AlerteAdmin", "AlerteCourriel", "AlerteJournalisee", "construire_alerte"]


def _corps(contexte: dict[str, Any]) -> str:
    """Contexte en texte lisible, une clé par ligne, ordre stable."""
    if not contexte:
        return "(aucun contexte)"
    return "\n".join(f"{cle} : {valeur}" for cle, valeur in sorted(contexte.items()))


class AlerteJournalisee:
    """Alerte écrite dans les logs en niveau ERROR.

    Repli permanent quand aucun destinataire n'est configuré.
    """

    async def envoyer(self, evenement: str, **contexte: Any) -> None:
        log.error(
            "alerte_admin",
            alerte=evenement,
            destinataire="absent",
            canal="log_uniquement_admin_non_configure",
            **contexte,
        )


class AlerteCourriel:
    """Alerte envoyée par email, et journalisée dans tous les cas.

    Le log part AVANT la tentative d'envoi : une alerte doit rester traçable
    dans les logs du VPS même si l'envoi échoue, et c'est le seul historique
    consultable après coup.
    """

    def __init__(self, destinataire: str, fournisseur: FournisseurCourriel) -> None:
        self.destinataire = destinataire
        self.fournisseur = fournisseur

    async def envoyer(self, evenement: str, **contexte: Any) -> None:
        log.error(
            "alerte_admin",
            alerte=evenement,
            destinataire=self.destinataire,
            canal="courriel",
            **contexte,
        )
        try:
            await self.fournisseur.envoyer_message(
                self.destinataire, f"[JobBot] {evenement}", _corps(contexte)
            )
        except Exception as exc:
            # Volontairement large : l'appelant est au milieu d'un chemin
            # d'erreur (plafond atteint, scraper cassé) et ne peut rien faire
            # de cette exception. Une alerte qui explose en signalant un
            # incident aggrave l'incident. Le log ci-dessus est déjà parti.
            log.error("alerte_admin_envoi_echoue", alerte=evenement, erreur=str(exc))


def construire_alerte(settings: Settings) -> AlerteAdmin:
    """Canal d'alerte à utiliser, selon la configuration."""
    if not settings.admin_courriel:
        return AlerteJournalisee()
    return AlerteCourriel(settings.admin_courriel, construire_fournisseur(settings))
