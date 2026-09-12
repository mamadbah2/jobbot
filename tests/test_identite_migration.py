"""Identité : email obligatoire, téléphone et telegram_id facultatifs (CLAUDE.md §5).

`phone` est passé nullable le 2026-09-12 (migration 0004) : le code à
6 chiffres ne prouve que la possession de l'adresse email, jamais celle d'un
numéro saisi au clavier — voir `src/core/auth/comptes.py`.

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
    assert colonnes["phone"].nullable is True
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
    assert etat["phone"] == "YES"
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
async def test_compte_sans_telephone_accepte(session: AsyncSession) -> None:
    """Le cœur de la tâche 18 : `phone` peut valoir NULL depuis la migration 0004."""
    session.add(User(email="g@test.invalid", full_name="G"))
    await session.commit()

    relu = (
        await session.execute(text("SELECT phone FROM users WHERE email = 'g@test.invalid'"))
    ).scalar_one()
    assert relu is None


@pytest.mark.integration
async def test_deux_comptes_sans_telephone_coexistent(session: AsyncSession) -> None:
    """Preuve que l'index unique sur `phone` tolère plusieurs NULL : sans ce
    test, le second compte sans téléphone serait rejeté par la contrainte
    d'unicité, et personne ne le verrait avant la production."""
    session.add(User(email="h@test.invalid", full_name="H"))
    session.add(User(email="i@test.invalid", full_name="I"))
    await session.commit()

    lignes = await session.execute(
        text(
            "SELECT phone FROM users WHERE email IN ('h@test.invalid', 'i@test.invalid')"
        )
    )
    assert [phone for (phone,) in lignes.all()] == [None, None]


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
