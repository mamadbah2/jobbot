"""Entrées et sorties de l'authentification.

`EmailStr` de pydantic n'est PAS utilisé : la validation et la normalisation
vivent dans `src/core/courriel_valide.py`, pour que le bot et l'API appliquent
exactement la même règle.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class DemandeCode(BaseModel):
    email: str = Field(min_length=1, max_length=320)


class VerificationCode(BaseModel):
    email: str = Field(min_length=1, max_length=320)
    code: str = Field(min_length=1, max_length=12)
    nom_complet: str | None = Field(default=None, max_length=255)


class Utilisateur(BaseModel):
    """Ce qu'un client a le droit de savoir d'un compte.

    Volontairement restreint : `token_version` et les identifiants internes
    n'ont aucune raison de sortir.
    """

    id: int
    email: str
    nom_complet: str | None
    etat: str

    @classmethod
    def depuis(cls, utilisateur: Any) -> Utilisateur:
        """Projette une ligne `users`. Ici plutôt que dans un router : deux
        routers en ont besoin, et importer une fonction privée d'un router
        depuis un autre recouplerait les deux."""
        return cls(
            id=utilisateur.id,
            email=utilisateur.email,
            nom_complet=utilisateur.full_name,
            etat=utilisateur.state,
        )
