"""Exceptions métier, traduites par chaque client (CLAUDE.md §4).

Chacune porte un `code` stable. L'API le renvoie tel quel, le client web le
traduit via ses propres libellés. Aucun texte destiné à un utilisateur ne doit
apparaître ici.
"""

from __future__ import annotations

from decimal import Decimal

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
    # Dollars DÉJÀ dépensés quand l'erreur est levée, le cas échéant. Porté ici
    # et non par la seule `CvIllisible` parce que la dépense peut survivre à
    # n'importe quel échec : un premier appel facturé, puis une panne de
    # DeepSeek sur le second (`AnalyseIndisponible`). Un coût qui ne voyage pas
    # avec l'exception est un coût que `usage_counters` ne verra jamais (§9).
    cout: Decimal | None = None


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

    def __init__(self, cout: Decimal | None = None) -> None:
        super().__init__(self.code)
        # Dollars déjà dépensés quand l'analyse abandonne après relance : deux
        # appels payés ne doivent pas disparaître du suivi de marge. Un attribut
        # et non une sous-classe : le statut HTTP se résout par type exact.
        self.cout = cout


class TropDAnalyses(ErreurMetier):
    """Plafond d'analyses du jour atteint. Distinct de `TropDeDemandes` :
    l'utilisateur n'a rien fait d'abusif, il a simplement épuisé un quota de
    coût, et le message à lui afficher n'est pas le même."""

    code = "trop_d_analyses"


class AnalyseIndisponible(ErreurMetier):
    """DeepSeek est injoignable. Le quota n'est pas décompté (§9).

    Rendre la place et consigner le coût sont deux décisions INDÉPENDANTES :
    l'utilisateur n'a rien reçu, donc sa place lui revient, mais une première
    tentative facturée avant la panne reste de l'argent dépensé — elle voyage
    dans `cout` (hérité de `ErreurMetier`)."""

    code = "analyse_indisponible"


class ProfilAbsent(ErreurMetier):
    """Correction demandée alors qu'aucun CV n'a jamais été déposé."""

    code = "profil_absent"
