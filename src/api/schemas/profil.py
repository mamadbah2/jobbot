"""Ce qu'un client a le droit de savoir d'un profil, et ce qu'il peut corriger.

Champs en français, comme `schemas/auth.py` et `schemas/offres.py`.
"""

from __future__ import annotations

from typing import Any, Final

from pydantic import BaseModel, Field

# Les listes corrigeables et leur plafond. SOURCE UNIQUE côté Python : ces trois
# nombres sont aussi connus du client web (`web/app/api-contrat.ts`), qui doit
# refuser AVANT d'appeler pour pouvoir dire laquelle déborde et de combien. Un
# test vérifie que les deux côtés ne divergent pas (`tests/test_textes_web.py`) :
# sans lui, l'écran laisserait passer ce que l'API refuse, et l'utilisateur
# tournerait en rond sur un message générique — la seule boucle sans sortie du
# parcours (revue finale, I-2).
LIMITES_LISTES: Final[dict[str, int]] = {
    "competences": 50,
    "langues": 20,
    "secteurs_vises": 20,
}


class ProfilVu(BaseModel):
    """`etat` vaut `absent` quand aucun CV n'a jamais été déposé — un cinquième
    état, propre au client : la base, elle, n'a pas de ligne du tout."""

    etat: str
    erreur: str | None = None
    structured: dict[str, Any] | None = None


class CorrectionProfil(BaseModel):
    """Les champs simples, modifiables en une soumission.

    Les expériences et formations n'y sont PAS : sans JavaScript, chaque ligne
    ajoutée coûte un aller-retour payé en data, et un formulaire d'expériences
    complet est l'écran où l'on abandonne (§11). On redépose le CV à la place.
    """

    nom_complet: str | None = Field(default=None, max_length=255)
    titre: str | None = Field(default=None, max_length=255)
    competences: list[str] = Field(
        default_factory=list, max_length=LIMITES_LISTES["competences"]
    )
    langues: list[str] = Field(default_factory=list, max_length=LIMITES_LISTES["langues"])
    secteurs_vises: list[str] = Field(
        default_factory=list, max_length=LIMITES_LISTES["secteurs_vises"]
    )
    mobilite: str | None = Field(default=None, max_length=255)
    type_contrat: str | None = Field(default=None, max_length=64)
