"""Écriture des offres en base (CLAUDE.md §5 et §7).

Les tests purs vérifient la mise en forme (empreinte, troncature, raw) et la
forme de l'upsert ; le comportement réel de `ON CONFLICT` demande un vrai
Postgres et vit derrière le marqueur `integration`.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy.dialects import postgresql

from src.ingest.base import JobDetail, OffreComplete, RawJob
from src.ingest.dedupe import compute_fingerprint
from src.ingest.store import (
    OffreInvalideError,
    construire_upsert,
    valeurs_offre,
)


def _offre(
    *,
    source_id: str = "503219",
    url: str = "https://www.emploidakar.com/offre-demploi/chef-de-parc/",
    title: str = "Chef de parc",
    company: str | None = "ACME SARL",
    location: str | None = "Dakar",
    raw: dict[str, object] | None = None,
    detail: JobDetail | None = None,
) -> OffreComplete:
    return OffreComplete(
        brut=RawJob(
            source="emploidakar",
            source_id=source_id,
            url=url,
            title=title,
            company=company,
            location=location,
            contract_type="CDI",
            raw=raw,
        ),
        detail=detail
        or JobDetail(
            description="Envoyez CV et LM à rh@acme.sn",
            posted_at=datetime(2026, 9, 1, tzinfo=UTC),
            apply_email="rh@acme.sn",
            apply_method="email",
        ),
    )


def test_calcule_l_empreinte_de_dedoublonnage() -> None:
    """§5 : `jobs.fingerprint` est renseigné à l'écriture, pas plus tard."""
    valeurs = valeurs_offre(_offre())
    assert valeurs["fingerprint"] == compute_fingerprint("Chef de parc", "ACME SARL", "Dakar")


def test_range_l_url_de_candidature_dans_raw() -> None:
    """Pas de colonne dédiée : le mode brouillon (§2.1) la relit depuis `raw`."""
    offre = _offre(
        detail=JobDetail(
            description="Postulez en ligne",
            apply_method="external",
            apply_url="https://recrutement.tiers.sn/offre/12",
        )
    )
    assert valeurs_offre(offre)["raw"]["apply_url"] == "https://recrutement.tiers.sn/offre/12"


def test_conserve_le_raw_de_la_page_de_liste() -> None:
    offre = _offre(raw={"job_type": "prestation"}, detail=JobDetail(description="x"))
    valeurs = valeurs_offre(offre)
    assert valeurs["raw"]["job_type"] == "prestation"
    assert "apply_url" not in valeurs["raw"]


def test_tronque_les_champs_trop_longs_plutot_que_de_perdre_la_passe() -> None:
    """Un titre à rallonge ne doit pas faire échouer l'écriture de toute la page."""
    valeurs = valeurs_offre(_offre(title="A" * 900))
    assert len(valeurs["title"]) == 512


def test_refuse_une_offre_sans_url() -> None:
    """`jobs.url` est unique et NOT NULL : une entrée sans lien est inexploitable."""
    with pytest.raises(OffreInvalideError):
        valeurs_offre(_offre(url=""))


def test_refuse_une_url_impossible_a_stocker() -> None:
    """Tronquer une URL produirait un lien mort en base : on écarte l'offre."""
    with pytest.raises(OffreInvalideError):
        valeurs_offre(_offre(url="https://exemple.sn/" + "a" * 1100))


def test_refuse_une_methode_de_candidature_inconnue() -> None:
    """§5 : `apply_method` porte un CHECK, autant échouer avant la base."""
    offre = _offre(detail=JobDetail(description="x", apply_method="telepathie"))
    with pytest.raises(OffreInvalideError):
        valeurs_offre(offre)


def test_l_upsert_vise_la_contrainte_source_source_id() -> None:
    sql = str(
        construire_upsert(valeurs_offre(_offre())).compile(dialect=postgresql.dialect())
    )
    assert "ON CONFLICT" in sql
    assert "uq_jobs_source_source_id" in sql


def test_l_upsert_met_a_jour_l_url_quand_elle_change() -> None:
    """Un changement de slug WordPress garde la même annonce (§5)."""
    sql = str(
        construire_upsert(valeurs_offre(_offre())).compile(dialect=postgresql.dialect())
    )
    apres_conflit = sql.split("ON CONFLICT", 1)[1]
    assert "url" in apres_conflit


def test_l_upsert_ne_reecrit_pas_la_date_de_creation() -> None:
    """`created_at` date la découverte de l'offre : la réécrire la ferait rajeunir."""
    sql = str(
        construire_upsert(valeurs_offre(_offre())).compile(dialect=postgresql.dialect())
    )
    assert "created_at" not in sql
