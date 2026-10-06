"""CV brut (texte ou image) → profil structuré + transcription.

Les deux chemins convergent : après analyse, une photo et un PDF ont rempli
exactement les mêmes colonnes. Rien dans la suite du produit n'a besoin de savoir
par où le profil est arrivé (spec §8).
"""

from __future__ import annotations

import base64
import json
from collections.abc import Awaitable, Callable
from decimal import Decimal
from typing import Any

from src.core.erreurs import CvIllisible
from src.llm.client import CoutAppel, modele_lit_les_images
from src.llm.prompts import PROMPT_CV, TEMPERATURE_CV, VERSION_PROMPT_CV
from src.logging_setup import get_logger

log = get_logger(__name__)

__all__ = ["CvIllisibleFacture", "VERSION_PROMPT_CV", "analyser_cv"]

Appelant = Callable[..., Awaitable[tuple[str, CoutAppel]]]

# La forme que la Phase 5 traitera comme source de vérité (§8.5). Un JSON
# syntaxiquement valide mais de mauvaise forme ne doit pas entrer en base : le
# post-contrôle anti-invention échouerait plus tard, loin de sa cause.
_CHAINES_OPTIONNELLES = (
    "nom_complet",
    "titre",
    "telephone",
    "mobilite",
    "pretention_salariale",
)


class CvIllisibleFacture(CvIllisible):
    """`CvIllisible` qui porte ce que les appels ont coûté.

    Deux appels ont été payés avant l'abandon : sans le montant, le cas le plus
    coûteux ne laisserait aucune trace dans le suivi de marge. Aucun contenu.
    """

    def __init__(self, cout: CoutAppel) -> None:
        super().__init__()
        self.cout = cout


def _nettoyer(brut: str) -> str:
    """Isole l'objet JSON : du premier `{` au dernier `}` (§9).

    Absorbe d'un coup les clôtures ```, y compris sur une seule ligne, et la
    prose que le modèle ajoute avant ou après.
    """
    debut, fin = brut.find("{"), brut.rfind("}")
    if debut == -1 or fin < debut:
        return brut.strip()
    return brut[debut : fin + 1]


def _liste_de_chaines(valeur: Any) -> bool:
    return isinstance(valeur, list) and all(isinstance(v, str) for v in valeur)


def _elements_valides(valeur: Any, obligatoires: tuple[str, ...], optionnelle: str) -> bool:
    """Chaque élément est un objet dont les clés obligatoires sont des chaînes.

    C'est `experiences[].entreprise` et `formations[].diplome` que le
    post-contrôle anti-invention de la Phase 5 lira (§8.5).
    """
    if not isinstance(valeur, list):
        return False
    for element in valeur:
        if not isinstance(element, dict):
            return False
        if not all(isinstance(element.get(c), str) for c in obligatoires):
            return False
        if element.get(optionnelle) is not None and not isinstance(
            element[optionnelle], str
        ):
            return False
    return True


def _valider(donnees: Any) -> dict[str, Any]:
    if not isinstance(donnees, dict):
        raise CvIllisible
    if not _elements_valides(donnees.get("experiences"), ("entreprise", "poste"), "periode"):
        raise CvIllisible
    if not _elements_valides(donnees.get("formations"), ("etablissement", "diplome"), "annee"):
        raise CvIllisible
    for cle in ("competences", "langues", "secteurs_vises"):
        if not _liste_de_chaines(donnees.get(cle)):
            raise CvIllisible
    for cle in _CHAINES_OPTIONNELLES:
        if cle not in donnees:
            raise CvIllisible
        if donnees[cle] is not None and not isinstance(donnees[cle], str):
            raise CvIllisible
    if not isinstance(donnees.get("transcription"), str):
        raise CvIllisible
    return donnees


def _messages(
    texte: str | None, image: bytes | None, type_image: str | None
) -> list[dict[str, Any]]:
    if image is not None:
        encodee = base64.b64encode(image).decode("ascii")
        contenu: list[dict[str, Any]] = [
            {"type": "text", "text": "Analyse ce CV."},
            {
                "type": "image_url",
                "image_url": {"url": f"data:image/{type_image};base64,{encodee}"},
            },
        ]
        return [
            {"role": "system", "content": PROMPT_CV},
            {"role": "user", "content": contenu},
        ]
    return [
        {"role": "system", "content": PROMPT_CV},
        {"role": "user", "content": texte or ""},
    ]


async def analyser_cv(
    *,
    texte: str | None = None,
    image: bytes | None = None,
    type_image: str | None = None,
    modele: str | None = None,
    appeler: Appelant,
) -> tuple[dict[str, Any], str, CoutAppel]:
    """Rend le profil structuré, la transcription, et le coût de l'appel.

    `appeler` est injecté : un test unitaire ne doit pas sortir sur le réseau.
    Une seule relance en cas de lecture impossible (§9) — pas zéro, pas trois :
    chaque relance est un appel payé.

    ATTENTION : le `CoutAppel` rendu AGRÈGE tous les appels faits (un ou deux),
    pas un seul. Il faut l'écrire tel quel dans `usage_counters`, sans le
    compter comme « un appel ». La relance est payée : ne compter que la
    dernière sous-estimerait la dépense réelle.

    Lève `ValueError` (erreur d'appelant, pas d'utilisateur) avant tout appel
    payant si l'entrée est inutilisable : ni texte ni image, image sans type, ou
    `modele` (quand il est donné) qui ne lit pas les images.
    """
    if texte is None and image is None:
        raise ValueError("ni texte ni image : l'appel serait payé pour rien")
    if image is not None:
        if not type_image:
            raise ValueError("type_image obligatoire avec une image")
        if modele is not None and not modele_lit_les_images(modele):
            raise ValueError(f"le modèle {modele!r} ne lit pas les images")
    messages = _messages(texte, image, type_image)
    total = CoutAppel(0, 0, 0, Decimal(0))

    for tentative in (1, 2):
        contenu, cout = await appeler(messages, temperature=TEMPERATURE_CV)
        total = CoutAppel(
            total.tokens_entree_cache + cout.tokens_entree_cache,
            total.tokens_entree_frais + cout.tokens_entree_frais,
            total.tokens_sortie + cout.tokens_sortie,
            total.cout_usd + cout.cout_usd,
        )
        try:
            profil = _valider(json.loads(_nettoyer(contenu)))
        except (json.JSONDecodeError, CvIllisible) as exc:
            # Aucun extrait de la réponse dans le journal : elle contient le CV.
            log.warning(
                "cv_reponse_illisible",
                tentative=tentative,
                type_erreur=type(exc).__name__,
                version_prompt=VERSION_PROMPT_CV,
            )
            continue
        transcription = str(profil.pop("transcription"))
        return profil, transcription, total

    # Montant et compteurs seulement : jamais de contenu, la réponse porte le CV.
    log.error(
        "cv_abandon_apres_relance",
        tokens_entree_cache=total.tokens_entree_cache,
        tokens_entree_frais=total.tokens_entree_frais,
        tokens_sortie=total.tokens_sortie,
        cout_usd=str(total.cout_usd),
        version_prompt=VERSION_PROMPT_CV,
    )
    # Levée hors de tout `except` : `__context__` reste vide, donc aucune trace
    # de la réponse (qui porte le CV) dans la chaîne d'exceptions.
    raise CvIllisibleFacture(total)
