"""Comptes utilisateurs (spec Phase 2 §8 et §9).

Deux règles portent tout le reste :

1. **Un seul endpoint pour l'inscription et la reconnexion.** C'est ce qui permet
   à `/auth/code/demande` de répondre exactement pareil que l'adresse existe ou
   non : sans cela, l'endpoint dirait publiquement qui est client.
2. **Un compte existant ignore les champs fournis.** Sinon `/auth/code/verifie`
   deviendrait un moyen d'écraser le numéro d'un compte — or ce numéro sert au
   paiement (§10) et à la liaison Telegram.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core import courriel_valide, telephone
from src.core.erreurs import (
    CompteInexistant,
    InscriptionIncomplete,
    TelephoneDejaUtilise,
)
from src.db.models import User


async def par_adresse(session: AsyncSession, adresse: str) -> User | None:
    resultat = await session.execute(
        select(User).where(User.email == courriel_valide.normaliser(adresse))
    )
    return resultat.scalar_one_or_none()


async def par_telephone(session: AsyncSession, numero: str) -> User | None:
    resultat = await session.execute(
        select(User).where(User.phone == telephone.normaliser(numero))
    )
    return resultat.scalar_one_or_none()


async def par_telegram(session: AsyncSession, telegram_id: int) -> User | None:
    resultat = await session.execute(select(User).where(User.telegram_id == telegram_id))
    return resultat.scalar_one_or_none()


async def connecter_ou_inscrire(
    session: AsyncSession,
    *,
    adresse: str,
    telephone_saisi: str | None = None,
    nom_complet: str | None = None,
) -> User:
    """Rend le compte existant, ou en crée un. L'adresse est déjà prouvée."""
    normalisee = courriel_valide.normaliser(adresse)

    existant = await par_adresse(session, normalisee)
    if existant is not None:
        return existant

    if not telephone_saisi or not nom_complet or not nom_complet.strip():
        raise InscriptionIncomplete(InscriptionIncomplete.code)

    numero = telephone.normaliser(telephone_saisi)
    if await par_telephone(session, numero) is not None:
        raise TelephoneDejaUtilise(TelephoneDejaUtilise.code)

    utilisateur = User(
        email=normalisee, phone=numero, full_name=nom_complet.strip(), state="onboarding"
    )
    session.add(utilisateur)
    await session.flush()
    return utilisateur


async def lier_telegram(session: AsyncSession, *, telephone_saisi: str, telegram_id: int) -> User:
    """Rattache un identifiant Telegram au compte portant ce numéro.

    Le numéro vient du bouton natif « partager mon contact » : Telegram l'a déjà
    vérifié. L'appelant DOIT avoir contrôlé que le contact appartient bien à
    l'expéditeur (`ContactUsurpe`) — ce module ne voit pas le message.
    """
    utilisateur = await par_telephone(session, telephone_saisi)
    if utilisateur is None:
        raise CompteInexistant(CompteInexistant.code)
    utilisateur.telegram_id = telegram_id
    await session.flush()
    return utilisateur


async def revoquer_jetons(session: AsyncSession, utilisateur: User) -> None:
    """Invalide d'un coup tous les jetons émis pour ce compte (§5)."""
    utilisateur.token_version += 1
    await session.flush()
