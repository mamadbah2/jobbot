"""Exceptions métier, traduites par chaque client (CLAUDE.md §4).

Chacune porte un `code` stable. L'API le renvoie tel quel, le bot le traduit via
`src/bot/texts.py`, le client web via ses propres libellés. Aucun texte destiné à
un utilisateur ne doit apparaître ici.
"""

from __future__ import annotations

__all__ = [
    "ErreurMetier",
    "NumeroInvalide",
    "AdresseInvalide",
    "TropDeDemandes",
    "PlafondGlobalAtteint",
    "CodeInvalide",
    "CodeExpire",
    "CompteInexistant",
    "InscriptionIncomplete",
    "TelephoneDejaUtilise",
    "ContactUsurpe",
    "JetonInvalide",
    "NomInvalide",
    "TelegramDejaLie",
    "EnvoiImpossible",
]


class ErreurMetier(Exception):
    """Racine des erreurs métier. `code` identifie le cas pour les clients."""

    code = "erreur_metier"


class NumeroInvalide(ErreurMetier, ValueError):
    code = "numero_invalide"


class AdresseInvalide(ErreurMetier, ValueError):
    code = "adresse_invalide"


class TropDeDemandes(ErreurMetier):
    """Un garde-fou du §10 de la spec a été atteint."""

    code = "trop_de_demandes"

    def __init__(self, *, attendre_secondes: int) -> None:
        super().__init__(self.code)
        self.attendre_secondes = attendre_secondes


class PlafondGlobalAtteint(ErreurMetier):
    """Plafond journalier de tout le service. Déclenche une alerte admin."""

    code = "plafond_global_atteint"


class CodeInvalide(ErreurMetier):
    code = "code_invalide"


class CodeExpire(ErreurMetier):
    """Code absent de Redis : expiré, jamais demandé, ou détruit après trop d'essais."""

    code = "code_expire"


class CompteInexistant(ErreurMetier):
    """Signal INTERNE. Ne doit jamais sortir de /auth/code/demande (spec §8)."""

    code = "compte_inexistant"


class InscriptionIncomplete(ErreurMetier):
    """Code valide, mais le compte est nouveau et nom/téléphone manquent."""

    code = "inscription_incomplete"


class TelephoneDejaUtilise(ErreurMetier):
    code = "telephone_deja_utilise"


class ContactUsurpe(ErreurMetier):
    """Contact Telegram partagé qui n'appartient pas à celui qui l'envoie."""

    code = "contact_usurpe"


class JetonInvalide(ErreurMetier):
    code = "jeton_invalide"


class NomInvalide(ErreurMetier, ValueError):
    code = "nom_invalide"


class TelegramDejaLie(ErreurMetier):
    """Cet identifiant Telegram est déjà rattaché à un autre compte."""

    code = "telegram_deja_lie"


class EnvoiImpossible(ErreurMetier):
    """Le fournisseur d'email a échoué. L'utilisateur peut réessayer."""

    code = "envoi_impossible"
