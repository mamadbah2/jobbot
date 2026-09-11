"""Comptes (spec Phase 2 §8 et §9).

Lancer avec : RUN_INTEGRATION_TESTS=1 pytest -m integration
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.core.auth import comptes
from src.core.erreurs import (
    AdresseInvalide,
    CompteInexistant,
    InscriptionIncomplete,
    NumeroInvalide,
    TelephoneDejaUtilise,
)
from src.db.models import User

ADRESSE = "fatou@jobbot-test.sn"
TEL = "+221771234567"


@pytest_asyncio.fixture
async def session(postgres_url: str) -> AsyncIterator[AsyncSession]:
    moteur = create_async_engine(postgres_url)
    fabrique = async_sessionmaker(moteur, expire_on_commit=False)
    async with fabrique() as session:
        await session.execute(delete(User).where(User.email.like("%@jobbot-test.sn")))
        await session.commit()
        yield session
        await session.rollback()
        await session.execute(delete(User).where(User.email.like("%@jobbot-test.sn")))
        await session.commit()
    await moteur.dispose()


@pytest.mark.integration
async def test_inscription_cree_le_compte(session: AsyncSession) -> None:
    u = await comptes.connecter_ou_inscrire(
        session, adresse=ADRESSE, telephone_saisi="77 123 45 67", nom_complet="Fatou Diop"
    )
    await session.commit()
    assert u.email == ADRESSE
    assert u.phone == TEL  # normalisé en E.164
    assert u.telegram_id is None
    assert u.token_version == 0
    assert u.state == "onboarding"


@pytest.mark.integration
async def test_reconnexion_ne_redemande_rien(session: AsyncSession) -> None:
    """Un utilisateur qui revient ne ressaisit jamais son numéro (spec §8)."""
    await comptes.connecter_ou_inscrire(
        session, adresse=ADRESSE, telephone_saisi=TEL, nom_complet="Fatou Diop"
    )
    await session.commit()
    u = await comptes.connecter_ou_inscrire(session, adresse=ADRESSE)
    assert u.phone == TEL
    assert u.full_name == "Fatou Diop"


@pytest.mark.integration
async def test_reconnexion_ignore_les_champs_fournis(session: AsyncSession) -> None:
    """Sinon /auth/code/verifie deviendrait un moyen d'écraser le numéro d'un compte."""
    await comptes.connecter_ou_inscrire(
        session, adresse=ADRESSE, telephone_saisi=TEL, nom_complet="Fatou Diop"
    )
    await session.commit()
    u = await comptes.connecter_ou_inscrire(
        session, adresse=ADRESSE, telephone_saisi="+221779999999", nom_complet="Autre Nom"
    )
    assert u.phone == TEL
    assert u.full_name == "Fatou Diop"


@pytest.mark.integration
async def test_inscription_sans_telephone_refusee(session: AsyncSession) -> None:
    with pytest.raises(InscriptionIncomplete):
        await comptes.connecter_ou_inscrire(session, adresse=ADRESSE, nom_complet="Fatou")


@pytest.mark.integration
async def test_inscription_sans_nom_refusee(session: AsyncSession) -> None:
    with pytest.raises(InscriptionIncomplete):
        await comptes.connecter_ou_inscrire(session, adresse=ADRESSE, telephone_saisi=TEL)


@pytest.mark.integration
async def test_telephone_deja_pris_par_un_autre_compte(session: AsyncSession) -> None:
    await comptes.connecter_ou_inscrire(
        session, adresse=ADRESSE, telephone_saisi=TEL, nom_complet="Fatou"
    )
    await session.commit()
    with pytest.raises(TelephoneDejaUtilise):
        await comptes.connecter_ou_inscrire(
            session, adresse="autre@jobbot-test.sn", telephone_saisi=TEL, nom_complet="Autre"
        )


@pytest.mark.integration
async def test_adresse_normalisee_avant_recherche(session: AsyncSession) -> None:
    await comptes.connecter_ou_inscrire(
        session, adresse=ADRESSE, telephone_saisi=TEL, nom_complet="Fatou"
    )
    await session.commit()
    u = await comptes.connecter_ou_inscrire(session, adresse="fatou@JOBBOT-TEST.SN")
    assert u.email == ADRESSE


@pytest.mark.integration
async def test_saisies_invalides_refusees(session: AsyncSession) -> None:
    with pytest.raises(AdresseInvalide):
        await comptes.connecter_ou_inscrire(session, adresse="pas-une-adresse")
    with pytest.raises(NumeroInvalide):
        await comptes.connecter_ou_inscrire(
            session, adresse=ADRESSE, telephone_saisi="+33612345678", nom_complet="Fatou"
        )


@pytest.mark.integration
async def test_liaison_telegram_retrouve_le_compte(session: AsyncSession) -> None:
    """Le cœur du §9 : pas de doublon entre le web et Telegram."""
    cree = await comptes.connecter_ou_inscrire(
        session, adresse=ADRESSE, telephone_saisi=TEL, nom_complet="Fatou"
    )
    await session.commit()
    lie = await comptes.lier_telegram(session, telephone_saisi="77 123 45 67", telegram_id=555)
    await session.commit()
    assert lie.id == cree.id
    assert lie.telegram_id == 555


@pytest.mark.integration
async def test_liaison_d_un_numero_inconnu(session: AsyncSession) -> None:
    with pytest.raises(CompteInexistant):
        await comptes.lier_telegram(session, telephone_saisi="+221770000000", telegram_id=555)


@pytest.mark.integration
async def test_liaison_idempotente(session: AsyncSession) -> None:
    await comptes.connecter_ou_inscrire(
        session, adresse=ADRESSE, telephone_saisi=TEL, nom_complet="Fatou"
    )
    await session.commit()
    await comptes.lier_telegram(session, telephone_saisi=TEL, telegram_id=555)
    await session.commit()
    encore = await comptes.lier_telegram(session, telephone_saisi=TEL, telegram_id=555)
    assert encore.telegram_id == 555


@pytest.mark.integration
async def test_revocation_incremente_la_version(session: AsyncSession) -> None:
    u = await comptes.connecter_ou_inscrire(
        session, adresse=ADRESSE, telephone_saisi=TEL, nom_complet="Fatou"
    )
    await session.commit()
    await comptes.revoquer_jetons(session, u)
    await session.commit()
    assert u.token_version == 1
