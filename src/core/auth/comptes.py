"""Comptes utilisateurs (spec Phase 2 §8 et §9).

Deux règles portent tout le reste :

1. **Un seul endpoint pour l'inscription et la reconnexion.** C'est ce qui permet
   à `/auth/code/demande` de répondre exactement pareil que l'adresse existe ou
   non : sans cela, l'endpoint dirait publiquement qui est client.
2. **Un compte existant ignore les champs fournis.** Sinon `/auth/code/verifie`
   deviendrait un moyen d'écraser le nom d'un compte existant.

Depuis le 2026-09-12, l'identité d'un compte est son adresse email, et rien
d'autre. Le numéro de téléphone a été retiré de `users` : le code à 6 chiffres
ne prouvait que la possession de l'adresse, jamais celle d'un numéro, et cette
confusion permettait de squatter le numéro d'autrui. Le numéro réapparaîtra en
Phase 3 dans `profiles.structured`, extrait du CV, sans prétention de
vérification. `telegram_id` est parti avec le client Telegram.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core import courriel_valide
from src.core.erreurs import InscriptionIncomplete, NomInvalide
from src.core.saisie import texte_saisi
from src.db.models import User


async def par_adresse(session: AsyncSession, adresse: str) -> User | None:
    resultat = await session.execute(
        select(User).where(User.email == courriel_valide.normaliser(adresse))
    )
    return resultat.scalar_one_or_none()


async def connecter_ou_inscrire(
    session: AsyncSession,
    *,
    adresse: str,
    nom_complet: str | None = None,
) -> User:
    """Rend le compte existant, ou en crée un. L'adresse est déjà prouvée."""
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
        # « Valider » sur une connexion instable (§11). Depuis la migration
        # 0005, `email` est la seule contrainte d'unicité de `users` (`phone`
        # et `telegram_id` sont partis avec elle, §5) : c'est donc la seule
        # que cet INSERT (`email`, `full_name`, `state`) peut heurter. Si
        # `deja` reste introuvable, la cause est autre et inconnue : on laisse
        # l'IntegrityError remonter plutôt que de la traduire en une erreur
        # métier qui mentirait.
        deja = await par_adresse(session, normalisee)
        if deja is not None:
            return deja
        raise
    return utilisateur


async def revoquer_jetons(session: AsyncSession, utilisateur: User) -> None:
    """Invalide d'un coup tous les jetons émis pour ce compte (§5)."""
    utilisateur.token_version += 1
    await session.flush()
