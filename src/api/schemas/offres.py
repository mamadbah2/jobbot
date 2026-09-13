"""Ce qu'un client a le droit de savoir d'une offre.

Projection **explicite** et non un dump du modèle : `description` pèse des
kilooctets par offre alors que la page a un budget de 200 Ko transférés
(CLAUDE.md §11), et `raw` est la charge brute rendue par le scraper — elle n'a
aucune raison de traverser.

Champs en français, comme `schemas/auth.py` : c'est la convention du dépôt.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class Offre(BaseModel):
    id: int
    titre: str
    entreprise: str | None
    lieu: str | None
    type_contrat: str | None
    publiee_le: datetime | None
    url: str
    methode_candidature: str

    @classmethod
    def depuis(cls, job: Any) -> Offre:
        return cls(
            id=job.id,
            titre=job.title,
            entreprise=job.company,
            lieu=job.location,
            type_contrat=job.contract_type,
            publiee_le=job.posted_at,
            url=job.url,
            methode_candidature=job.apply_method,
        )


class PageOffres(BaseModel):
    offres: list[Offre]
    total: int
