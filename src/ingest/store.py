"""Écriture des offres collectées dans `jobs` (CLAUDE.md §5).

Le worker repasse toutes les 2 h sur une source qui republie les mêmes
annonces : l'écriture est donc un upsert sur `(source, source_id)`, jamais un
insert simple. `jobs.url` porte en plus sa propre contrainte d'unicité, ce qui
donne deux cas à distinguer :

- l'annonce a changé d'URL (slug WordPress réécrit) → même `(source, source_id)`,
  l'upsert met l'URL à jour ;
- une autre annonce occupe déjà cette URL → conflit irréductible. L'offre est
  écartée et comptée, jamais propagée : une collision ne doit pas faire perdre
  le reste de la passe.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import Insert, insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import APPLY_METHODS, Job
from src.ingest.base import OffreComplete
from src.ingest.dedupe import compute_fingerprint
from src.logging_setup import get_logger

log = get_logger(__name__)

CONTRAINTE_SOURCE = "uq_jobs_source_source_id"

# Longueurs des colonnes VARCHAR de `jobs` (§5). Un champ trop long est tronqué
# plutôt que de faire échouer l'écriture de toute la page.
LONGUEUR_URL = 1024
_LONGUEURS = {
    "title": 512,
    "company": 255,
    "location": 255,
    "contract_type": 64,
    "apply_email": 320,
}

# Colonnes rafraîchies à chaque passe. `created_at` en est exclu : il date la
# découverte de l'offre et la réécrire la ferait rajeunir à chaque cycle.
_COLONNES_MISES_A_JOUR = (
    "url",
    "title",
    "company",
    "location",
    "contract_type",
    "description",
    "apply_email",
    "apply_method",
    "posted_at",
    "fingerprint",
    "raw",
)


class OffreInvalideError(ValueError):
    """Offre inexploitable en base : elle est écartée, pas propagée."""


@dataclass(frozen=True, slots=True)
class ResultatEcriture:
    """Bilan d'une écriture : ce qui est en base, ce qui a été écarté."""

    ecrites: int
    ignorees: int


def _tronquer(valeur: str | None, longueur: int) -> str | None:
    if valeur is None:
        return None
    return valeur[:longueur]


def valeurs_offre(offre: OffreComplete) -> dict[str, Any]:
    """Traduit une offre collectée en ligne de `jobs`.

    Lève `OffreInvalideError` si la ligne ne peut pas exister en base : c'est
    l'appelant qui décide d'écarter l'offre, sans perdre les autres.
    """
    brut, detail = offre.brut, offre.detail

    url = brut.url.strip()
    if not url:
        raise OffreInvalideError(f"offre {brut.source}/{brut.source_id} sans URL")
    if len(url) > LONGUEUR_URL:
        # Tronquer produirait un lien mort en base, donc une candidature perdue.
        raise OffreInvalideError(f"URL trop longue pour {brut.source}/{brut.source_id}")
    if detail.apply_method not in APPLY_METHODS:
        raise OffreInvalideError(f"apply_method inconnue : {detail.apply_method!r}")

    # `apply_url` n'a pas de colonne dédiée (§5) : elle vit dans `raw`, d'où le
    # mode brouillon la relira pour envoyer l'utilisateur sur le bon formulaire.
    raw: dict[str, Any] = dict(brut.raw or {})
    if detail.apply_url:
        raw["apply_url"] = detail.apply_url

    return {
        "source": brut.source,
        "source_id": brut.source_id,
        "url": url,
        "title": _tronquer(brut.title, _LONGUEURS["title"]),
        "company": _tronquer(brut.company, _LONGUEURS["company"]),
        "location": _tronquer(brut.location, _LONGUEURS["location"]),
        "contract_type": _tronquer(brut.contract_type, _LONGUEURS["contract_type"]),
        "description": detail.description,
        "apply_email": _tronquer(detail.apply_email, _LONGUEURS["apply_email"]),
        "apply_method": detail.apply_method,
        "posted_at": detail.posted_at,
        "fingerprint": compute_fingerprint(brut.title, brut.company, brut.location),
        "raw": raw,
    }


def construire_upsert(valeurs: dict[str, Any]) -> Insert:
    """Insert ... ON CONFLICT (source, source_id) DO UPDATE."""
    requete = insert(Job).values(**valeurs)
    return requete.on_conflict_do_update(
        constraint=CONTRAINTE_SOURCE,
        set_={colonne: requete.excluded[colonne] for colonne in _COLONNES_MISES_A_JOUR},
    )


async def charger_source_ids(session: AsyncSession, source: str) -> set[str]:
    """Identifiants déjà connus pour une source — alimente la pagination (§7)."""
    resultat = await session.execute(select(Job.source_id).where(Job.source == source))
    return set(resultat.scalars().all())


async def enregistrer_offres(
    session: AsyncSession, offres: Iterable[OffreComplete]
) -> ResultatEcriture:
    """Écrit les offres une à une, sans qu'une ligne fautive perde les autres.

    Chaque écriture est encadrée par un point de sauvegarde : un conflit sur
    `jobs.url` annule cette offre seule, la transaction de la passe survit.
    """
    ecrites = 0
    ignorees = 0

    for offre in offres:
        try:
            valeurs = valeurs_offre(offre)
        except OffreInvalideError as exc:
            log.warning(
                "offre_ecartee",
                source=offre.brut.source,
                source_id=offre.brut.source_id,
                raison=str(exc),
            )
            ignorees += 1
            continue

        try:
            async with session.begin_nested():
                await session.execute(construire_upsert(valeurs))
        except IntegrityError as exc:
            # Cas connu : `jobs.url` déjà pris par une autre annonce. On ne
            # supprime pas la ligne existante — des candidatures y sont liées.
            log.warning(
                "offre_en_conflit",
                source=offre.brut.source,
                source_id=offre.brut.source_id,
                url=valeurs["url"],
                erreur=str(exc.orig),
            )
            ignorees += 1
            continue
        ecrites += 1

    return ResultatEcriture(ecrites=ecrites, ignorees=ignorees)
