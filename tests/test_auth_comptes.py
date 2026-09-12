"""Comptes (spec Phase 2 §8 et §9).

Depuis le 2026-09-12, `connecter_ou_inscrire` ne prend plus de numéro de
téléphone (migration 0004 : le code à 6 chiffres ne prouve que la possession
de l'adresse email, jamais celle d'un numéro saisi au clavier). Le téléphone
se pose désormais via `definir_telephone`, sur un compte déjà identifié, et
`lier_telegram` prend directement cet utilisateur plutôt que de le retrouver
par son numéro.

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
    InscriptionIncomplete,
    NomInvalide,
    NumeroInvalide,
    TelegramDejaLie,
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
    u = await comptes.connecter_ou_inscrire(session, adresse=ADRESSE, nom_complet="Fatou Diop")
    await session.commit()
    assert u.email == ADRESSE
    assert u.telegram_id is None
    assert u.token_version == 0
    assert u.state == "onboarding"


@pytest.mark.integration
async def test_inscription_sans_telephone_reussit(session: AsyncSession) -> None:
    """Le cœur de la tâche 18 : le téléphone n'est plus demandé à l'inscription,
    et `phone` vaut bien NULL en base — pas une chaîne vide ni une valeur
    fabriquée."""
    u = await comptes.connecter_ou_inscrire(session, adresse=ADRESSE, nom_complet="Fatou Diop")
    await session.commit()
    assert u.phone is None

    relu = await comptes.par_adresse(session, ADRESSE)
    assert relu is not None
    assert relu.phone is None


@pytest.mark.integration
async def test_deux_comptes_sans_telephone_coexistent(session: AsyncSession) -> None:
    """Preuve que l'index unique sur `phone` tolère plusieurs NULL (migration
    0004) : sans elle, le second compte serait rejeté par la contrainte
    d'unicité, et personne ne le verrait avant la production."""
    premier = await comptes.connecter_ou_inscrire(
        session, adresse=ADRESSE, nom_complet="Fatou Diop"
    )
    await session.commit()
    second = await comptes.connecter_ou_inscrire(
        session, adresse="autre@jobbot-test.sn", nom_complet="Autre Personne"
    )
    await session.commit()

    assert premier.phone is None
    assert second.phone is None
    assert premier.id != second.id


@pytest.mark.integration
async def test_reconnexion_ne_redemande_rien(session: AsyncSession) -> None:
    """Un utilisateur qui revient ne ressaisit jamais son nom (spec §8)."""
    await comptes.connecter_ou_inscrire(session, adresse=ADRESSE, nom_complet="Fatou Diop")
    await session.commit()
    u = await comptes.connecter_ou_inscrire(session, adresse=ADRESSE)
    assert u.full_name == "Fatou Diop"


@pytest.mark.integration
async def test_reconnexion_ignore_les_champs_fournis(session: AsyncSession) -> None:
    """Sinon /auth/code/verifie deviendrait un moyen d'écraser le nom d'un compte."""
    await comptes.connecter_ou_inscrire(session, adresse=ADRESSE, nom_complet="Fatou Diop")
    await session.commit()
    u = await comptes.connecter_ou_inscrire(session, adresse=ADRESSE, nom_complet="Autre Nom")
    assert u.full_name == "Fatou Diop"


@pytest.mark.integration
async def test_inscription_sans_nom_refusee(session: AsyncSession) -> None:
    with pytest.raises(InscriptionIncomplete):
        await comptes.connecter_ou_inscrire(session, adresse=ADRESSE)


@pytest.mark.integration
async def test_adresse_normalisee_avant_recherche(session: AsyncSession) -> None:
    await comptes.connecter_ou_inscrire(session, adresse=ADRESSE, nom_complet="Fatou")
    await session.commit()
    u = await comptes.connecter_ou_inscrire(session, adresse="fatou@JOBBOT-TEST.SN")
    assert u.email == ADRESSE


@pytest.mark.integration
async def test_adresse_invalide_refusee(session: AsyncSession) -> None:
    with pytest.raises(AdresseInvalide):
        await comptes.connecter_ou_inscrire(session, adresse="pas-une-adresse")


@pytest.mark.integration
async def test_definir_telephone_pose_le_numero(session: AsyncSession) -> None:
    u = await comptes.connecter_ou_inscrire(session, adresse=ADRESSE, nom_complet="Fatou")
    await session.commit()
    assert u.phone is None

    maj = await comptes.definir_telephone(session, utilisateur=u, telephone_saisi="77 123 45 67")
    await session.commit()
    assert maj.id == u.id
    assert maj.phone == TEL  # normalisé en E.164


@pytest.mark.integration
async def test_definir_telephone_deja_utilise_par_un_autre_compte(session: AsyncSession) -> None:
    proprietaire = await comptes.connecter_ou_inscrire(
        session, adresse=ADRESSE, nom_complet="Fatou"
    )
    autre = await comptes.connecter_ou_inscrire(
        session, adresse="autre@jobbot-test.sn", nom_complet="Autre"
    )
    await session.commit()
    await comptes.definir_telephone(session, utilisateur=proprietaire, telephone_saisi=TEL)
    await session.commit()

    with pytest.raises(TelephoneDejaUtilise):
        await comptes.definir_telephone(session, utilisateur=autre, telephone_saisi=TEL)


@pytest.mark.integration
async def test_definir_telephone_reste_idempotent_sur_le_meme_compte(
    session: AsyncSession,
) -> None:
    """Reposer sur soi-même le numéro qu'on porte déjà doit passer : ce n'est
    pas « un autre compte » qui le porte."""
    u = await comptes.connecter_ou_inscrire(session, adresse=ADRESSE, nom_complet="Fatou")
    await session.commit()
    await comptes.definir_telephone(session, utilisateur=u, telephone_saisi=TEL)
    await session.commit()

    encore = await comptes.definir_telephone(session, utilisateur=u, telephone_saisi=TEL)
    assert encore.phone == TEL


@pytest.mark.integration
async def test_definir_telephone_numero_invalide_refuse(session: AsyncSession) -> None:
    u = await comptes.connecter_ou_inscrire(session, adresse=ADRESSE, nom_complet="Fatou")
    await session.commit()
    with pytest.raises(NumeroInvalide):
        await comptes.definir_telephone(session, utilisateur=u, telephone_saisi="+33612345678")


@pytest.mark.integration
async def test_liaison_telegram_attache_l_utilisateur_fourni(session: AsyncSession) -> None:
    """Le cœur du §9 depuis le 2026-09-12 : `lier_telegram` ne recherche plus
    aucun compte par numéro, c'est l'appelant qui fournit `utilisateur` déjà
    identifié."""
    cree = await comptes.connecter_ou_inscrire(session, adresse=ADRESSE, nom_complet="Fatou")
    await session.commit()

    lie = await comptes.lier_telegram(session, utilisateur=cree, telegram_id=555)
    await session.commit()
    assert lie.id == cree.id
    assert lie.telegram_id == 555


@pytest.mark.integration
async def test_liaison_idempotente(session: AsyncSession) -> None:
    u = await comptes.connecter_ou_inscrire(session, adresse=ADRESSE, nom_complet="Fatou")
    await session.commit()
    await comptes.lier_telegram(session, utilisateur=u, telegram_id=555)
    await session.commit()
    encore = await comptes.lier_telegram(session, utilisateur=u, telegram_id=555)
    assert encore.telegram_id == 555


@pytest.mark.integration
async def test_liaison_telegram_deja_rattache_a_un_autre_compte(session: AsyncSession) -> None:
    premier = await comptes.connecter_ou_inscrire(session, adresse=ADRESSE, nom_complet="Fatou")
    second = await comptes.connecter_ou_inscrire(
        session, adresse="autre@jobbot-test.sn", nom_complet="Autre"
    )
    await session.commit()
    await comptes.lier_telegram(session, utilisateur=premier, telegram_id=555)
    await session.commit()

    with pytest.raises(TelegramDejaLie):
        await comptes.lier_telegram(session, utilisateur=second, telegram_id=555)


@pytest.mark.integration
async def test_revocation_incremente_la_version(session: AsyncSession) -> None:
    u = await comptes.connecter_ou_inscrire(session, adresse=ADRESSE, nom_complet="Fatou")
    await session.commit()
    await comptes.revoquer_jetons(session, u)
    await session.commit()
    assert u.token_version == 1


@pytest.mark.integration
@pytest.mark.parametrize("nom_invalide", [12345, ["Fatou"]])
async def test_nom_de_type_inattendu_leve_nom_invalide(
    session: AsyncSession, nom_invalide: object
) -> None:
    """`core` est la frontière de confiance : un type inattendu doit lever une
    erreur métier, jamais une AttributeError (donc une 500)."""
    with pytest.raises(NomInvalide):
        await comptes.connecter_ou_inscrire(
            session,
            adresse=ADRESSE,
            nom_complet=nom_invalide,  # type: ignore[arg-type]
        )


@pytest.mark.integration
async def test_nom_trop_long_refuse_sans_creer_de_ligne(session: AsyncSession) -> None:
    """256 caractères : au-delà de la colonne `users.full_name` (String(255))."""
    with pytest.raises(NomInvalide):
        await comptes.connecter_ou_inscrire(session, adresse=ADRESSE, nom_complet="A" * 256)
    await session.commit()
    assert await comptes.par_adresse(session, ADRESSE) is None


@pytest.mark.integration
async def test_nom_de_longueur_maximale_accepte(session: AsyncSession) -> None:
    """255 caractères exactement : la borne, pas au-delà."""
    u = await comptes.connecter_ou_inscrire(session, adresse=ADRESSE, nom_complet="A" * 255)
    assert u.full_name == "A" * 255


@pytest.mark.integration
async def test_course_a_l_inscription_traduite(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Double clic sur « Valider » sur une connexion instable (§11) : la
    deuxième requête doit retrouver le compte, jamais laisser fuir
    l'IntegrityError de la contrainte d'unicité sur `email`."""
    cree = await comptes.connecter_ou_inscrire(session, adresse=ADRESSE, nom_complet="Fatou")
    await session.commit()

    original_par_adresse = comptes.par_adresse
    appels = {"n": 0}

    async def par_adresse_en_retard(s: AsyncSession, adresse: str) -> User | None:
        appels["n"] += 1
        if appels["n"] == 1:
            # Simule le SELECT d'une requête concurrente qui n'a pas encore vu
            # la ligne créée par `cree` ci-dessus.
            return None
        return await original_par_adresse(s, adresse)

    monkeypatch.setattr(comptes, "par_adresse", par_adresse_en_retard)

    retrouve = await comptes.connecter_ou_inscrire(session, adresse=ADRESSE, nom_complet="Fatou")
    assert retrouve.id == cree.id
