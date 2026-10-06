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
from src.llm.client import CoutAppel
from src.llm.prompts import PROMPT_CV, VERSION_PROMPT_CV
from src.logging_setup import get_logger

log = get_logger(__name__)

__all__ = ["VERSION_PROMPT_CV", "analyser_cv"]

Appelant = Callable[..., Awaitable[tuple[str, CoutAppel]]]

# La forme que la Phase 5 traitera comme source de vérité (§8.5). Un JSON
# syntaxiquement valide mais de mauvaise forme ne doit pas entrer en base : le
# post-contrôle anti-invention échouerait plus tard, loin de sa cause.
_LISTES = ("experiences", "formations", "competences", "langues", "secteurs_vises")
_CHAINES_OPTIONNELLES = (
    "nom_complet",
    "titre",
    "telephone",
    "mobilite",
    "pretention_salariale",
)


def _nettoyer(brut: str) -> str:
    """Retire les clôtures de code dont le modèle entoure souvent son JSON (§9)."""
    texte = brut.strip()
    if texte.startswith("```"):
        texte = texte.split("\n", 1)[-1] if "\n" in texte else ""
        if texte.rstrip().endswith("```"):
            texte = texte.rstrip()[: -len("```")]
    return texte.strip()


def _valider(donnees: Any) -> dict[str, Any]:
    if not isinstance(donnees, dict):
        raise CvIllisible
    for cle in _LISTES:
        if not isinstance(donnees.get(cle), list):
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
    appeler: Appelant,
) -> tuple[dict[str, Any], str, CoutAppel]:
    """Rend le profil structuré, la transcription, et le coût de l'appel.

    `appeler` est injecté : un test unitaire ne doit pas sortir sur le réseau.
    Une seule relance en cas de lecture impossible (§9) — pas zéro, pas trois :
    chaque relance est un appel payé.

    Le coût rendu est la somme des tentatives : la relance est payée, et ne
    compter que la dernière sous-estimerait la dépense réelle.
    """
    messages = _messages(texte, image, type_image)
    total = CoutAppel(0, 0, 0, Decimal(0))

    for tentative in (1, 2):
        contenu, cout = await appeler(messages)
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

    # Levée hors de tout `except` : `__context__` reste vide, donc aucune trace
    # de la réponse (qui porte le CV) dans la chaîne d'exceptions.
    raise CvIllisible
