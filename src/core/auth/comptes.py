"""Comptes utilisateurs (spec Phase 2 §8 et §9).

Deux règles portent tout le reste :

1. **Un seul endpoint pour l'inscription et la reconnexion.** C'est ce qui permet
   à `/auth/code/demande` de répondre exactement pareil que l'adresse existe ou
   non : sans cela, l'endpoint dirait publiquement qui est client.
2. **Un compte existant ignore les champs fournis.** Sinon `/auth/code/verifie`
   deviendrait un moyen d'écraser le nom d'un compte existant.

Depuis le 2026-09-12, ce module ne prend plus de numéro de téléphone à
l'inscription ni pour la liaison Telegram (migration 0004) : le code à
6 chiffres ne prouvait que la possession de l'adresse email, jamais celle
d'un numéro saisi au clavier, et cette confusion permettait de squatter le
numéro d'autrui. Le téléphone n'est posé que par `definir_telephone`, à
partir d'un canal qui le certifie lui-même (liaison Telegram aujourd'hui,
webhook mobile money en Phase 6).
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core import courriel_valide, telephone
from src.core.erreurs import (
    InscriptionIncomplete,
    NomInvalide,
    TelegramDejaLie,
    TelephoneDejaUtilise,
)
from src.core.saisie import texte_saisi
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
    nom_complet: str | None = None,
) -> User:
    """Rend le compte existant, ou en crée un. L'adresse est déjà prouvée.

    Ne prend plus de numéro de téléphone depuis le 2026-09-12 : un numéro saisi
    ici ne serait prouvé par rien (le code à 6 chiffres ne prouve que la
    possession de l'adresse), et permettait de squatter le numéro d'autrui —
    voir la migration 0004. Le téléphone se pose désormais uniquement via
    `definir_telephone`, à partir d'un canal qui le certifie.
    """
    normalisee = courriel_valide.normaliser(adresse)

    existant = await par_adresse(session, normalisee)
    if existant is not None:
        return existant

    if not nom_complet:
        raise InscriptionIncomplete(InscriptionIncomplete.code)

    # `nom_complet` est une saisie utilisateur non fiable : borne de 255, taille
    # de la colonne `users.full_name` (§5). Un type inattendu (int, liste) doit
    # produire `NomInvalide`, jamais une `AttributeError` ni une `DataError`.
    nom = texte_saisi(nom_complet, longueur_max=255, erreur=NomInvalide, sujet="nom")

    utilisateur = User(email=normalisee, full_name=nom, state="onboarding")
    try:
        # SAVEPOINT : seul l'INSERT est annulé en cas de course, pas toute la
        # transaction extérieure (contrairement à un `session.rollback()`).
        async with session.begin_nested():
            session.add(utilisateur)
            await session.flush()
    except IntegrityError:
        # Course : une requête concurrente a créé le compte entre notre SELECT
        # et notre INSERT. Fréquent quand l'utilisateur tape deux fois sur
        # « Valider » sur une connexion instable (§11). La seule contrainte
        # d'unicité que cet INSERT peut heurter est désormais `email` (le
        # téléphone n'est plus posé ici) : si `deja` reste introuvable, la
        # cause est autre et inconnue, on laisse l'IntegrityError remonter
        # plutôt que de la traduire en une erreur métier qui mentirait sur
        # la cause.
        deja = await par_adresse(session, normalisee)
        if deja is not None:
            return deja
        raise
    return utilisateur


async def lier_telegram(session: AsyncSession, *, utilisateur: User, telegram_id: int) -> User:
    """Rattache un identifiant Telegram à un utilisateur déjà identifié.

    Depuis le 2026-09-12, cette fonction NE recherche PLUS de compte par
    numéro de téléphone : c'était le vecteur d'une usurpation — un attaquant
    s'inscrivait avec le numéro d'une victime, qui se serait alors vue
    rattachée, via cette même fonction, au compte de l'attaquant en partageant
    son contact Telegram. L'appelant doit désormais avoir déjà identifié
    `utilisateur` par un canal fiable (session web authentifiée, jeton de
    liaison à usage unique) avant d'appeler cette fonction.
    """
    proprietaire = await par_telegram(session, telegram_id)
    if proprietaire is not None and proprietaire.id != utilisateur.id:
        raise TelegramDejaLie(TelegramDejaLie.code)

    utilisateur.telegram_id = telegram_id
    await session.flush()
    return utilisateur


async def definir_telephone(
    session: AsyncSession, *, utilisateur: User, telephone_saisi: str
) -> User:
    """Pose un numéro vérifié sur un compte déjà identifié.

    Cette fonction NE VÉRIFIE PAS que le numéro appartient à `utilisateur` —
    elle ne le peut pas. L'appelant doit avoir obtenu ce numéro d'un canal qui
    le vérifie lui-même : aujourd'hui uniquement le bouton natif « partager mon
    contact » de Telegram (Telegram certifie que le numéro appartient à
    l'expéditeur), et le webhook mobile money en Phase 6. Ne jamais l'appeler
    avec un numéro simplement saisi au clavier par l'utilisateur.
    """
    numero = telephone.normaliser(telephone_saisi)
    proprietaire = await par_telephone(session, numero)
    if proprietaire is not None and proprietaire.id != utilisateur.id:
        raise TelephoneDejaUtilise(TelephoneDejaUtilise.code)

    utilisateur.phone = numero
    await session.flush()
    return utilisateur


async def revoquer_jetons(session: AsyncSession, utilisateur: User) -> None:
    """Invalide d'un coup tous les jetons émis pour ce compte (§5)."""
    utilisateur.token_version += 1
    await session.flush()
