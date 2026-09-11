"""Authentification par email + code à 6 chiffres (spec Phase 2 §8).

`/auth/code/demande` ne consulte JAMAIS la base : il doit répondre exactement
pareil que l'adresse existe ou non, sinon il devient un annuaire public de la
clientèle. Toute la logique « ce compte existe-t-il ? » vit dans
`/auth/code/verifie`, derrière la preuve de possession de l'adresse.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status

from src.alerting import AlerteAdmin, construire_alerte
from src.api import deps
from src.api.schemas.auth import DemandeCode
from src.config import Settings, get_settings
from src.core import courriel_valide
from src.core.auth import cles, codes
from src.core.auth.limites import ReglesEnvoi, autoriser_envoi
from src.core.cache import CacheRedis
from src.courriel.provider import FournisseurCourriel, construire_fournisseur
from src.logging_setup import get_logger

log = get_logger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])


def reglages() -> Settings:
    return get_settings()


def fournisseur(
    settings: Annotated[Settings, Depends(reglages)],
) -> FournisseurCourriel:
    """Surchargeable dans les tests, pour ne jamais rien envoyer."""
    return construire_fournisseur(settings)


def alerte(settings: Annotated[Settings, Depends(reglages)]) -> AlerteAdmin:
    return construire_alerte(settings)


def _regles(settings: Settings) -> ReglesEnvoi:
    return ReglesEnvoi(
        cooldown_secondes=settings.auth_cooldown_secondes,
        par_heure=settings.auth_envois_par_heure,
        par_jour=settings.auth_envois_par_jour,
        par_ip_heure=settings.auth_envois_par_ip_heure,
        plafond_global_jour=settings.auth_plafond_global_jour,
    )


@router.post("/code/demande", status_code=status.HTTP_202_ACCEPTED)
async def demander_code(
    corps: DemandeCode,
    request: Request,
    response: Response,
    cache: Annotated[CacheRedis, Depends(deps.cache_redis)],
    settings: Annotated[Settings, Depends(reglages)],
    envoi: Annotated[FournisseurCourriel, Depends(fournisseur)],
    canal_alerte: Annotated[AlerteAdmin, Depends(alerte)],
) -> None:
    """Envoie un code. Réponse identique que l'adresse existe ou non."""
    adresse = courriel_valide.normaliser(corps.email)
    ip = request.client.host if request.client else "inconnue"

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
    await envoi.envoyer_code(adresse, code)

    # Jamais le code, jamais l'adresse en clair : ce log sert au suivi des
    # abandons d'onboarding (§11), pas au débogage d'un compte.
    log.info("code_demande", domaine=adresse.rsplit("@", 1)[-1])
    response.status_code = status.HTTP_202_ACCEPTED
