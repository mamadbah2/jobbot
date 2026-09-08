"""Upsert des offres sur un vrai Postgres (CLAUDE.md §5).

`ON CONFLICT` et les contraintes uniques ne s'observent pas hors base :
ces tests demandent la base migrée.

Lancer avec : RUN_INTEGRATION_TESTS=1 pytest -m integration
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.db.models import Job
from src.ingest.base import JobDetail, OffreComplete, RawJob
from src.ingest.store import charger_source_ids, enregistrer_offres

SOURCE = "source_de_test"


def _offre(source_id: str, url: str, *, titre: str = "Chef de parc") -> OffreComplete:
    return OffreComplete(
        brut=RawJob(source=SOURCE, source_id=source_id, url=url, title=titre),
        detail=JobDetail(description="Envoyez CV et LM à rh@acme.sn", apply_email="rh@acme.sn"),
    )


@pytest_asyncio.fixture
async def session(postgres_url: str) -> AsyncIterator[AsyncSession]:
    """Session isolée : les offres de test sont retirées à la sortie."""
    moteur = create_async_engine(postgres_url)
    fabrique = async_sessionmaker(moteur, expire_on_commit=False)
    async with fabrique() as session:
        await session.execute(delete(Job).where(Job.source == SOURCE))
        await session.commit()
        yield session
        await session.execute(delete(Job).where(Job.source == SOURCE))
        await session.commit()
    await moteur.dispose()


@pytest.mark.integration
async def test_insere_puis_relit_les_identifiants_connus(session: AsyncSession) -> None:
    await enregistrer_offres(session, [_offre("1", "https://x.sn/a"), _offre("2", "https://x.sn/b")])
    await session.commit()
    assert await charger_source_ids(session, SOURCE) == {"1", "2"}


@pytest.mark.integration
async def test_une_seconde_passe_met_a_jour_sans_dupliquer(session: AsyncSession) -> None:
    await enregistrer_offres(session, [_offre("1", "https://x.sn/a")])
    resultat = await enregistrer_offres(
        session, [_offre("1", "https://x.sn/a", titre="Chef de parc (H/F)")]
    )
    await session.commit()
    lignes = (await session.execute(select(Job).where(Job.source == SOURCE))).scalars().all()
    assert len(lignes) == 1
    assert lignes[0].title == "Chef de parc (H/F)"
    assert resultat.ecrites == 1


@pytest.mark.integration
async def test_suit_le_changement_d_url_d_une_meme_annonce(session: AsyncSession) -> None:
    """Un slug WordPress modifié ne doit pas créer une seconde offre (§5)."""
    await enregistrer_offres(session, [_offre("1", "https://x.sn/ancien-slug")])
    await enregistrer_offres(session, [_offre("1", "https://x.sn/nouveau-slug")])
    await session.commit()
    lignes = (await session.execute(select(Job).where(Job.source == SOURCE))).scalars().all()
    assert [ligne.url for ligne in lignes] == ["https://x.sn/nouveau-slug"]


@pytest.mark.integration
async def test_une_url_deja_prise_par_une_autre_offre_ne_perd_pas_la_passe(
    session: AsyncSession,
) -> None:
    """`jobs.url` est unique : le conflit est écarté et compté, pas propagé."""
    await enregistrer_offres(session, [_offre("1", "https://x.sn/a")])
    resultat = await enregistrer_offres(
        session, [_offre("2", "https://x.sn/a"), _offre("3", "https://x.sn/c")]
    )
    await session.commit()
    ids = await charger_source_ids(session, SOURCE)
    assert ids == {"1", "3"}
    assert resultat.ecrites == 1
    assert resultat.ignorees == 1
