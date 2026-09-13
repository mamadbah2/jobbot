"""Exceptions métier, traduites par chaque client (CLAUDE.md §4).

Chacune porte un `code` stable. L'API le renvoie tel quel, le client web le
traduit via ses propres libellés. Aucun texte destiné à un utilisateur ne doit
apparaître ici.
"""

from __future__ import annotations

__all__ = [
    "ErreurMetier",
    "AdresseInvalide",
    "TropDeDemandes",
    "PlafondGlobalAtteint",
    "CodeInvalide",
    "CodeExpire",
    "InscriptionIncomplete",
    "JetonInvalide",
    "NomInvalide",
    "EnvoiImpossible",
]


class ErreurMetier(Exception):
    """Racine des erreurs métier. `code` identifie le cas pour les clients."""

    code = "erreur_metier"


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
    """Code absent de Redis : expiré, ou jamais demandé."""

    code = "code_expire"


class InscriptionIncomplete(ErreurMetier):
    """Code valide, mais le compte est nouveau et le nom manque."""

    code = "inscription_incomplete"


class JetonInvalide(ErreurMetier):
    code = "jeton_invalide"


class NomInvalide(ErreurMetier, ValueError):
    code = "nom_invalide"


class EnvoiImpossible(ErreurMetier):
    """Le fournisseur d'email a échoué. L'utilisateur peut réessayer."""

    code = "envoi_impossible"
