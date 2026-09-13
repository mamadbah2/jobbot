"""Identité : email seule identité de connexion (CLAUDE.md §5).

`phone` et `telegram_id` ont été supprimées par la migration 0005
(2026-09-12) : Telegram cesse d'être un client du produit, et un numéro
saisi au clavier n'est prouvé par rien — voir `src/core/auth/comptes.py`.

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
async def test_les_colonnes_telephone_et_telegram_ont_disparu(session: AsyncSession) -> None:
    """Migration 0005 : `users` n'a plus que l'adresse email comme identité."""
    etat = dict(
        (
            await session.execute(
                text(
                    "SELECT column_name, is_nullable FROM information_schema.columns "
                    "WHERE table_name = 'users'"
                )
            )
        ).all()
    )
    assert "phone" not in etat
    assert "telegram_id" not in etat
    assert etat["email"] == "NO"


@pytest.mark.integration
async def test_adresse_en_double_refusee(session: AsyncSession) -> None:
    session.add(User(email="d@test.invalid", full_name="D"))
    await session.commit()
    session.add(User(email="d@test.invalid", full_name="D2"))
    with pytest.raises(IntegrityError):
        await session.commit()
