"""Migrations Alembic — nécessite un Postgres réel.

Lancer avec : RUN_INTEGRATION_TESTS=1 pytest -m integration
"""

from __future__ import annotations

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import create_async_engine

from src.db.models import Base

TABLES_ATTENDUES = {
    "users",
    "profiles",
    "subscriptions",
    "jobs",
    "applications",
    "usage_counters",
    "job_application_stats",
}

# §5 : ces index ne sont pas optionnels.
INDEX_OBLIGATOIRES = {
    "jobs": {"ix_jobs_fingerprint", "ix_jobs_posted_at"},
    "applications": {"ix_applications_user_id"},
    "subscriptions": {"ix_subscriptions_expires_at"},
}


@pytest.mark.integration
async def test_schema_complet(postgres_url: str) -> None:
    """La base migrée contient les 7 tables et les index obligatoires."""
    engine = create_async_engine(postgres_url)
    try:
        async with engine.connect() as conn:
            tables = await conn.run_sync(lambda c: set(inspect(c).get_table_names()))
            assert tables >= TABLES_ATTENDUES

            for table, index_attendus in INDEX_OBLIGATOIRES.items():
                noms = await conn.run_sync(
                    lambda c, t=table: {i["name"] for i in inspect(c).get_indexes(t)}
                )
                assert index_attendus <= noms, f"index manquant sur {table}"
    finally:
        await engine.dispose()


@pytest.mark.integration
async def test_unicite_candidature_par_offre(postgres_url: str) -> None:
    """§5 : un utilisateur ne peut postuler qu'une fois à une même offre."""
    engine = create_async_engine(postgres_url)
    try:
        async with engine.connect() as conn:
            contraintes = await conn.run_sync(
                lambda c: {u["name"] for u in inspect(c).get_unique_constraints("applications")}
            )
            assert "uq_applications_user_job" in contraintes
    finally:
        await engine.dispose()


@pytest.mark.integration
async def test_check_contraint_statut_applique(postgres_url: str) -> None:
    """Les CHECK remplacent les ENUM natifs : ils doivent réellement rejeter."""
    engine = create_async_engine(postgres_url)
    try:
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO users (email, phone, telegram_id, token_version, language, state) "
                    "VALUES (:email, :phone, :tg, 0, 'fr', 'onboarding')"
                ),
                {"email": "check@test.invalid", "phone": "+221779990001", "tg": 999_001},
            )
            with pytest.raises(Exception, match="ck_users_state|check constraint"):
                await conn.execute(
                    text(
                        "INSERT INTO users "
                        "(email, phone, telegram_id, token_version, language, state) "
                        "VALUES (:email, :phone, :tg, 0, 'fr', 'etat_invalide')"
                    ),
                    {"email": "check2@test.invalid", "phone": "+221779990002", "tg": 999_002},
                )
    finally:
        await engine.dispose()


def test_metadata_couvre_les_tables_attendues() -> None:
    """Contrôle hors base : les modèles déclarent bien les 7 tables du §5."""
    assert set(Base.metadata.tables) >= TABLES_ATTENDUES
