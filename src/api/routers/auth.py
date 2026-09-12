"""Authentification par email + code à 6 chiffres (spec Phase 2 §8).

`/auth/code/demande` ne consulte JAMAIS la base : il doit répondre exactement
pareil que l'adresse existe ou non, sinon il devient un annuaire public de la
clientèle. Toute la logique « ce compte existe-t-il ? » vit dans
`/auth/code/verifie`, derrière la preuve de possession de l'adresse.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.api import deps
from src.api.schemas.auth import DemandeCode, Utilisateur, VerificationCode
from src.config import Settings
from src.core import courriel_valide
from src.core.alerte import AlerteAdmin
from src.core.auth import cles, codes, comptes, jetons
from src.core.auth.limites import (
    ReglesEnvoi,
    ReglesVerification,
    autoriser_envoi,
    autoriser_verification,
    compter_code_invalide,
)
from src.core.cache import CacheRedis
from src.core.erreurs import CodeInvalide, EnvoiImpossible, ErreurMetier
from src.courriel.provider import FournisseurCourriel, construire_fournisseur
from src.db.models import User
from src.logging_setup import get_logger

log = get_logger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])


def fournisseur(
    settings: Annotated[Settings, Depends(deps.reglages)],
) -> FournisseurCourriel:
    """Surchargeable dans les tests, pour ne jamais rien envoyer."""
    return construire_fournisseur(settings)


def _regles(settings: Settings) -> ReglesEnvoi:
    return ReglesEnvoi(
        cooldown_secondes=settings.auth_cooldown_secondes,
        par_heure=settings.auth_envois_par_heure,
        par_jour=settings.auth_envois_par_jour,
        par_ip_heure=settings.auth_envois_par_ip_heure,
        plafond_global_jour=settings.auth_plafond_global_jour,
    )


def _regles_verification(settings: Settings) -> ReglesVerification:
    return ReglesVerification(
        par_heure=settings.auth_verifications_par_heure,
        par_ip_heure=settings.auth_verifications_par_ip_heure,
    )


@router.post("/code/demande", status_code=status.HTTP_202_ACCEPTED)
async def demander_code(
    corps: DemandeCode,
    response: Response,
    cache: Annotated[CacheRedis, Depends(deps.cache_redis)],
    settings: Annotated[Settings, Depends(deps.reglages)],
    envoi: Annotated[FournisseurCourriel, Depends(fournisseur)],
    canal_alerte: Annotated[AlerteAdmin, Depends(deps.alerte)],
    ip: Annotated[str, Depends(deps.ip_cliente)],
) -> None:
    """Envoie un code. Réponse identique que l'adresse existe ou non."""
    adresse = courriel_valide.normaliser(corps.email)

    # Une clé dérivée par usage (tâche 5) : le même JWT_SECRET ne doit pas
    # alimenter en clair la signature des jetons, le hachage des codes et
    # celui des clés de limitation — une faiblesse sur l'un compromettrait
    # les deux autres (src/core/auth/cles.py).
    secret_brut = settings.jwt_secret.get_secret_value()
    cle_limite = cles.deriver(secret_brut, "limite")
    cle_code = cles.deriver(secret_brut, "code")

    await autoriser_envoi(
        cache,
        adresse=adresse,
        ip=ip,
        regles=_regles(settings),
        secret=cle_limite,
        alerte=canal_alerte,
    )

    code = codes.generer_code()
    await codes.deposer(
        cache,
        adresse,
        code,
        secret=cle_code,
        ttl_secondes=settings.code_ttl_secondes,
    )
    try:
        await envoi.envoyer_code(adresse, code)
    except Exception as exc:  # noqa: BLE001 — tout échec du fournisseur
        # Ne jamais échouer en silence (§7) : un fournisseur en panne bloque
        # toutes les inscriptions, et personne ne s'en apercevrait avant que
        # les utilisateurs ne se plaignent. Les compteurs déjà consommés ne
        # sont PAS remboursés : l'utilisateur réessaiera après le cooldown.
        await canal_alerte.envoyer("envoi_courriel_echoue", domaine=adresse.rsplit("@", 1)[-1])
        # Le message brut du fournisseur n'est PAS journalisé : une erreur SMTP
        # embarque couramment le destinataire (« 550 no such user <adresse> »),
        # ce qui ferait fuiter une donnée personnelle dans les logs (§14.4).
        # La classe de l'exception suffit à distinguer une panne de connexion
        # d'un rejet ; le détail par message vit chez le fournisseur.
        log.error("envoi_courriel_echoue", type_erreur=type(exc).__name__)
        raise EnvoiImpossible(EnvoiImpossible.code) from exc

    # Jamais le code, jamais l'adresse en clair : ce log sert au suivi des
    # abandons d'onboarding (§11), pas au débogage d'un compte.
    log.info("code_demande", domaine=adresse.rsplit("@", 1)[-1])
    response.status_code = status.HTTP_202_ACCEPTED


def poser_cookie(response: Response, utilisateur: User, settings: Settings) -> None:
    """Dépose le jeton de session.

    `httponly` : un cookie lisible en JavaScript est volable par la moindre
    faille XSS. `samesite=lax` : suffisant puisque `web` et `api` partagent
    l'origine (§4). `secure` uniquement en production, où l'on est en HTTPS.
    """
    secret_brut = settings.jwt_secret.get_secret_value()
    jeton = jetons.encoder(
        user_id=utilisateur.id,
        token_version=utilisateur.token_version,
        secret=cles.deriver(secret_brut, "jeton"),
        duree_jours=settings.jwt_duree_jours,
    )
    response.set_cookie(
        settings.cookie_session_nom,
        jeton,
        max_age=settings.jwt_duree_jours * 86400,
        httponly=True,
        samesite="lax",
        secure=settings.cookie_session_secure,
        path="/",
    )


@router.post("/code/verifie")
async def verifier_code(
    corps: VerificationCode,
    response: Response,
    session: Annotated[AsyncSession, Depends(deps.session_db)],
    cache: Annotated[CacheRedis, Depends(deps.cache_redis)],
    settings: Annotated[Settings, Depends(deps.reglages)],
    ip: Annotated[str, Depends(deps.ip_cliente)],
) -> Utilisateur:
    """Inscrit ou connecte. Un seul endpoint pour les deux cas (spec §8)."""
    secret_brut = settings.jwt_secret.get_secret_value()
    adresse = courriel_valide.normaliser(corps.email)
    cle_limite = cles.deriver(secret_brut, "limite")
    regles = _regles_verification(settings)

    # Plafond de CADENCE, indexé sur la seule IP : consommé avant toute preuve
    # de possession de l'adresse, un compteur par adresse ici permettrait à
    # n'importe qui connaissant l'email d'une victime de bloquer ses
    # connexions en la martelant avec des codes bidon (round de correction 1).
    await autoriser_verification(cache, ip=ip, regles=regles, secret=cle_limite)

    try:
        await codes.verifier(
            cache,
            adresse,
            corps.code,
            secret=cles.deriver(secret_brut, "code"),
        )
    except CodeInvalide:
        # Le code existait et il est faux : c'est une tentative de devinette,
        # elle compte contre le plafond par adresse. Un code absent
        # (`CodeExpire`) ne consomme rien : sinon un tiers pourrait épuiser le
        # quota d'une victime sans rien posséder (round de correction 1).
        await compter_code_invalide(cache, adresse=adresse, regles=regles, secret=cle_limite)
        raise

    try:
        utilisateur = await comptes.connecter_ou_inscrire(
            session,
            adresse=adresse,
            nom_complet=corps.nom_complet,
        )
    except ErreurMetier:
        # `verifier` a déjà consommé le code, avant même que `connecter_ou_inscrire`
        # ne soit appelé. `InscriptionIncomplete` (nom manquant) et `NomInvalide`
        # sont des erreurs de SAISIE : l'utilisateur doit pouvoir corriger et
        # resoumettre sans redemander un email, attendre le cooldown et entamer
        # son quota d'envois (§11 : l'abandon en onboarding est le risque
        # principal). Depuis le 2026-09-12, `connecter_ou_inscrire` ne prend
        # plus de téléphone : `NumeroInvalide` et `TelephoneDejaUtilise` ne
        # peuvent plus être levées ici (elles restent possibles côté
        # `comptes.definir_telephone`, appelée ailleurs, une fois le compte
        # identifié).
        await codes.deposer(
            cache,
            adresse,
            corps.code,
            secret=cles.deriver(secret_brut, "code"),
            ttl_secondes=settings.code_ttl_secondes,
        )
        raise

    poser_cookie(response, utilisateur, settings)
    log.info("compte_connecte", user_id=utilisateur.id, etat=utilisateur.state)
    return Utilisateur.depuis(utilisateur)


@router.post("/deconnexion", status_code=status.HTTP_204_NO_CONTENT)
async def deconnexion(
    response: Response,
    utilisateur: Annotated[User, Depends(deps.utilisateur_courant)],
    session: Annotated[AsyncSession, Depends(deps.session_db)],
    settings: Annotated[Settings, Depends(deps.reglages)],
) -> None:
    """Invalide TOUS les jetons du compte, pas seulement celui-ci (spec §5)."""
    await comptes.revoquer_jetons(session, utilisateur)
    # `secure` et `samesite` doivent reprendre ceux posés par `poser_cookie` :
    # un navigateur n'efface le cookie que si les attributs correspondent,
    # sinon un cookie fantôme reste (round de correction 1, tâche 14). Sans
    # conséquence de sécurité ici — la révocation tient à `token_version`,
    # pas à la suppression du cookie.
    response.delete_cookie(
        settings.cookie_session_nom,
        path="/",
        httponly=True,
        samesite="lax",
        secure=settings.cookie_session_secure,
    )
