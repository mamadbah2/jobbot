"""Identité : email et téléphone obligatoires, telegram_id facultatif (CLAUDE.md §5).

Lancer avec : RUN_INTEGRATION_TESTS=1 pytest -m integration
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy import delete, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.db.models import User


def test_modele_user_declare_la_nouvelle_identite() -> None:
    colonnes = {c.name: c for c in User.__table__.columns}
    assert colonnes["email"].nullable is False
    assert colonnes["phone"].nullable is False
    assert colonnes["telegram_id"].nullable is True
    assert colonnes["token_version"].nullable is False
    assert colonnes["token_version"].default.arg == 0


@pytest_asyncio.fixture
async def session(postgres_url: str) -> AsyncIterator[AsyncSession]:
    moteur = create_async_engine(postgres_url)
    fabrique = async_sessionmaker(moteur, expire_on_commit=False)
    async with fabrique() as session:
        await session.execute(delete(User).where(User.email.like("%@test.invalid")))
        await session.commit()
        yield session
        # Un test de doublon laisse la session DEACTIVE après l'IntegrityError
        # attrapée par `pytest.raises` : il faut la réarmer avant de réutiliser
        # la session pour le nettoyage (sémantique SQLAlchemy async).
        await session.rollback()
        await session.execute(delete(User).where(User.email.like("%@test.invalid")))
        await session.commit()
    await moteur.dispose()


@pytest.mark.integration
async def test_colonnes_presentes_en_base(session: AsyncSession) -> None:
    lignes = await session.execute(
        text(
            "SELECT column_name, is_nullable FROM information_schema.columns "
            "WHERE table_name = 'users'"
        )
    )
    etat = {nom: nullable for nom, nullable in lignes.all()}
    assert etat["email"] == "NO"
    assert etat["phone"] == "NO"
    assert etat["telegram_id"] == "YES"
    assert etat["token_version"] == "NO"


@pytest.mark.integration
async def test_compte_sans_telegram_accepte(session: AsyncSession) -> None:
    session.add(User(email="a@test.invalid", phone="+221771111111", full_name="A"))
    await session.commit()


@pytest.mark.integration
async def test_deux_comptes_sans_telegram_acceptes(session: AsyncSession) -> None:
    """Un index unique tolère plusieurs NULL : sinon un seul compte web serait possible."""
    session.add(User(email="b@test.invalid", phone="+221772222222", full_name="B"))
    session.add(User(email="c@test.invalid", phone="+221773333333", full_name="C"))
    await session.commit()


@pytest.mark.integration
async def test_adresse_en_double_refusee(session: AsyncSession) -> None:
    session.add(User(email="d@test.invalid", phone="+221774444444", full_name="D"))
    await session.commit()
    session.add(User(email="d@test.invalid", phone="+221775555555", full_name="D2"))
    with pytest.raises(IntegrityError):
        await session.commit()


@pytest.mark.integration
async def test_telephone_en_double_refuse(session: AsyncSession) -> None:
    session.add(User(email="e@test.invalid", phone="+221776666666", full_name="E"))
    await session.commit()
    session.add(User(email="f@test.invalid", phone="+221776666666", full_name="F"))
    with pytest.raises(IntegrityError):
        await session.commit()
