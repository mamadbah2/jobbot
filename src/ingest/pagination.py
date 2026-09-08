"""Politique de pagination incrémentale (CLAUDE.md §7).

Le worker passe toutes les 2 h et le site publie quelques offres par jour :
parcourir les 14 pages et rouvrir les 238 annonces à chaque fois coûterait
17 min pour presque rien, et multiplierait les requêtes chez un tiers (§2.4).

On descend donc les pages tant qu'elles apportent du nouveau. Le signal
d'arrêt est **une page entièrement connue**, jamais une seule offre connue :
un site peut remonter une annonce en tête de liste, ce qui stopperait la
passe trop tôt et ferait manquer toutes les offres situées en dessous.
"""

from __future__ import annotations

from collections.abc import Iterable
from collections.abc import Set as AbstractSet
from dataclasses import dataclass

from src.ingest.base import RawJob


@dataclass(frozen=True, slots=True)
class DecisionPage:
    """Ce qu'il reste à traiter d'une page, et s'il faut demander la suivante."""

    nouvelles: tuple[RawJob, ...]
    continuer: bool


def analyser_page(offres: Iterable[RawJob], ids_connus: AbstractSet[str]) -> DecisionPage:
    """Filtre les offres déjà en base et décide si la pagination continue."""
    nouvelles: list[RawJob] = []
    vus: set[str] = set()
    vide = True

    for offre in offres:
        vide = False
        # La dérive de pagination peut renvoyer deux fois la même offre.
        if offre.source_id in vus:
            continue
        vus.add(offre.source_id)
        if offre.source_id not in ids_connus:
            nouvelles.append(offre)

    return DecisionPage(nouvelles=tuple(nouvelles), continuer=not vide and bool(nouvelles))
