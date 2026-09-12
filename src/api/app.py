"""Construction de l'application FastAPI (CLAUDE.md §4).

L'API ne fait que traduire `src/core/` en HTTP. Les erreurs métier y arrivent
sous forme d'exceptions et en ressortent sous forme de **codes stables** — jamais
de phrases : les textes destinés à l'utilisateur vivent chez chaque client (§4).
"""

from __future__ import annotations

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from src.api.routers import auth, moi, sante
from src.core.erreurs import (
    AdresseInvalide,
    CodeExpire,
    CodeInvalide,
    CompteInexistant,
    EnvoiImpossible,
    ErreurMetier,
    InscriptionIncomplete,
    JetonInvalide,
    NomInvalide,
    PlafondGlobalAtteint,
    TropDeDemandes,
)
from src.logging_setup import get_logger

log = get_logger(__name__)

# Les bornes des schémas pydantic n'agissent qu'après le parsing complet du
# corps : sur un endpoint public non authentifié, ça laisse n'importe qui
# faire lire des mégaoctets au serveur avant tout rejet. 64 Ko est très large
# pour du JSON d'authentification ; l'upload de CV de la Phase 3 aura sa
# propre limite, plus haute, propre à sa route.
TAILLE_CORPS_MAX = 64 * 1024

# Chaque erreur métier a un statut HTTP, et un seul. Le défaut est 400 :
# une erreur non listée est une faute de saisie, pas une panne serveur.
_STATUTS: dict[type[ErreurMetier], int] = {
    # HTTP_422_UNPROCESSABLE_CONTENT est le nom actuel : HTTP_422_UNPROCESSABLE_ENTITY
    # (celui du brief) est marqué déprécié par Starlette dans la version installée
    # ici et lève un avertissement à l'import — même valeur numérique (422).
    AdresseInvalide: status.HTTP_422_UNPROCESSABLE_CONTENT,
    NomInvalide: status.HTTP_422_UNPROCESSABLE_CONTENT,
    InscriptionIncomplete: status.HTTP_422_UNPROCESSABLE_CONTENT,
    TropDeDemandes: status.HTTP_429_TOO_MANY_REQUESTS,
    PlafondGlobalAtteint: status.HTTP_503_SERVICE_UNAVAILABLE,
    JetonInvalide: status.HTTP_401_UNAUTHORIZED,
    CompteInexistant: status.HTTP_404_NOT_FOUND,
    EnvoiImpossible: status.HTTP_503_SERVICE_UNAVAILABLE,
    # Explicites depuis que /auth/code/verifie les lève réellement : un choix,
    # pas le défaut 400 par omission (revue finale, corrections mineures).
    CodeInvalide: status.HTTP_400_BAD_REQUEST,
    CodeExpire: status.HTTP_400_BAD_REQUEST,
}


def create_app() -> FastAPI:
    # docs/redoc/openapi désactivés : surface d'attaque inutile ici, les seuls
    # clients de cette API sont écrits dans ce même dépôt.
    app = FastAPI(title="JobBot", docs_url=None, redoc_url=None, openapi_url=None)

    @app.exception_handler(ErreurMetier)
    async def _erreur_metier(request: Request, exc: Exception) -> JSONResponse:
        assert isinstance(exc, ErreurMetier)
        code_http = _STATUTS.get(type(exc), status.HTTP_400_BAD_REQUEST)
        entetes = {}
        if isinstance(exc, TropDeDemandes):
            entetes["Retry-After"] = str(exc.attendre_secondes)
        return JSONResponse(
            status_code=code_http, content={"erreur": exc.code}, headers=entetes
        )

    @app.exception_handler(Exception)
    async def _exception_non_rattrapee(request: Request, exc: Exception) -> JSONResponse:
        """Filet de sécurité (IMPORTANT 7, revue finale).

        `src/api/main.py` passe `log_config=None` à uvicorn : sans ce
        gestionnaire, une exception non rattrapée serait journalisée par la
        bibliothèque standard avec sa trace complète. Sur une erreur
        SQLAlchemy, `__str__` embarque couramment les paramètres liés
        (adresse, numéro — §14.4). On ne journalise donc QUE le nom du type,
        jamais le message ni la trace.

        Ne concerne ni les `ErreurMetier` (gestionnaire dédié ci-dessus,
        prioritaire par résolution de type exacte de Starlette) ni les
        `HTTPException` de FastAPI/Starlette (gestionnaires par défaut, même
        raison).
        """
        log.error("exception_non_rattrapee", type_erreur=type(exc).__name__)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"erreur": "erreur_interne"},
        )

    @app.middleware("http")
    async def _borner_le_corps(request: Request, appeler_suite):  # type: ignore[no-untyped-def]
        """Refuse un corps démesuré avant de le bufferiser.

        Les bornes des schémas pydantic n'agissent qu'après le parsing complet :
        sur un endpoint public non authentifié, cela laisse n'importe qui faire
        lire des mégaoctets au serveur. 64 Ko est très large pour du JSON
        d'authentification ; l'upload de CV de la Phase 3 aura sa propre limite.
        """
        if request.method in ("POST", "PUT", "PATCH"):
            longueur = request.headers.get("content-length")
            if longueur is None:
                return JSONResponse(
                    status_code=status.HTTP_411_LENGTH_REQUIRED,
                    content={"erreur": "longueur_requise"},
                )
            try:
                if int(longueur) > TAILLE_CORPS_MAX:
                    raise ValueError
            except ValueError:
                return JSONResponse(
                    status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                    content={"erreur": "corps_trop_grand"},
                )
        return await appeler_suite(request)

    app.include_router(sante.router)
    app.include_router(auth.router)
    app.include_router(moi.router)
    return app
