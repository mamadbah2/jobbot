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
    "CvTypeRefuse",
    "CvTropGros",
    "CvSansTexte",
    "CvIllisible",
    "TropDAnalyses",
    "AnalyseIndisponible",
    "ProfilAbsent",
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


class CvTypeRefuse(ErreurMetier):
    """Le fichier n'est ni un PDF, ni un DOCX, ni une image JPEG ou PNG."""

    code = "cv_type_refuse"


class CvTropGros(ErreurMetier):
    code = "cv_trop_gros"


class CvSansTexte(ErreurMetier):
    """Document sans texte exploitable : PDF scanné, page blanche.

    Levée AVANT tout appel au LLM : c'est le seul moment où l'on peut refuser
    sans rien payer.
    """

    code = "cv_sans_texte"


class CvIllisible(ErreurMetier):
    """Fichier annoncé valide par ses octets de tête mais inexploitable :
    PDF chiffré, archive tronquée, ZIP qui n'est pas un document Word."""

    code = "cv_illisible"


class TropDAnalyses(ErreurMetier):
    """Plafond d'analyses du jour atteint. Distinct de `TropDeDemandes` :
    l'utilisateur n'a rien fait d'abusif, il a simplement épuisé un quota de
    coût, et le message à lui afficher n'est pas le même."""

    code = "trop_d_analyses"


class AnalyseIndisponible(ErreurMetier):
    """DeepSeek est injoignable. Le quota n'est pas décompté (§9)."""

    code = "analyse_indisponible"


class ProfilAbsent(ErreurMetier):
    """Correction demandée alors qu'aucun CV n'a jamais été déposé."""

    code = "profil_absent"
