"""Ce qu'un client a le droit de savoir d'un profil, et ce qu'il peut corriger.

Champs en français, comme `schemas/auth.py` et `schemas/offres.py`.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


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
    competences: list[str] = Field(default_factory=list, max_length=50)
    langues: list[str] = Field(default_factory=list, max_length=20)
    secteurs_vises: list[str] = Field(default_factory=list, max_length=20)
    mobilite: str | None = Field(default=None, max_length=255)
    type_contrat: str | None = Field(default=None, max_length=64)
