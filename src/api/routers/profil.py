"""Profil : dépôt du CV, consultation, correction (spec §7).

Tout ce qui peut être refusé l'est **dans la requête**, avant qu'un seul token
soit payé : taille, type réel, plafond du jour, absence de texte. L'analyse
elle-même part en arrière-plan et la route rend la main tout de suite —
l'utilisateur est sur une 3G comptée, il ne doit jamais attendre un appel LLM.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated, Any

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, File, Response, UploadFile, status
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.api import deps
from src.api.schemas.profil import CorrectionProfil, ProfilVu
from src.config import Settings, get_settings
from src.core import cv_fichier
from src.core.auth import cles
from src.core.cv_etat import etat_affiche
from src.core.cv_limites import autoriser_analyse_cv
from src.core.erreurs import CvTropGros, ProfilAbsent
from src.db.models import Profile, UsageCounter, User
from src.db.session import session_scope
from src.llm.client import appeler_deepseek
from src.llm.cv_parser import analyser_cv
from src.logging_setup import get_logger

log = get_logger(__name__)
router = APIRouter(tags=["profil"])

# `asyncio` ne retient qu'une référence FAIBLE vers une tâche : sans cet
# ensemble, le ramasse-miettes peut emporter l'analyse en plein vol.
_TACHES_DE_FOND: set[asyncio.Task[None]] = set()

_PREFIXE_IMAGE = "jobbot:cv:image"


def _vue(profil: Profile | None) -> ProfilVu:
    if profil is None:
        return ProfilVu(etat="absent")
    return ProfilVu(
        etat=profil.parse_etat, erreur=profil.parse_erreur, structured=profil.structured
    )


async def _profil_de(session: AsyncSession, user_id: int) -> Profile | None:
    return (
        await session.execute(select(Profile).where(Profile.user_id == user_id))
    ).scalar_one_or_none()


@router.get("/profil")
async def voir_profil(
    utilisateur: Annotated[User, Depends(deps.utilisateur_courant)],
    session: Annotated[AsyncSession, Depends(deps.session_db)],
    settings: Annotated[Settings, Depends(deps.reglages)],
) -> ProfilVu:
    """Une analyse `en_cours` depuis trop longtemps est présentée comme échouée.

    C'est ce qui remplace un balayeur de tâches zombies : si `api` redémarre en
    pleine analyse, rien ne reprend le travail, et l'écran le dit au lieu de
    faire tourner l'utilisateur dans une attente sans fin (spec §6).
    """
    profil = await _profil_de(session, utilisateur.id)
    if profil is None:
        return ProfilVu(etat="absent")
    etat, erreur = etat_affiche(
        profil.parse_etat,
        profil.parse_demarre_le,
        profil.parse_erreur,
        maintenant=datetime.now(UTC),
        delai_max_secondes=settings.cv_analyse_delai_max_secondes,
    )
    return ProfilVu(etat=etat, erreur=erreur, structured=profil.structured)


async def consigner_cout(
    session: AsyncSession,
    user_id: int,
    *,
    tokens_entree: int,
    tokens_sortie: int,
    cout_usd: Decimal,
) -> None:
    """Ajoute un appel au compteur du mois (§9 : coût de chaque appel consigné).

    Un upsert qui INCRÉMENTE côté base, appuyé sur `uq_usage_counters_user_period` :
    lire puis écrire ouvrirait une course entre deux analyses simultanées, l'une
    écrasant l'ajout de l'autre. `cout_usd` reste un `Decimal` de bout en bout :
    un `float` introduirait une erreur d'arrondi dans un compteur d'argent.
    """
    periode = datetime.now(UTC).strftime("%Y-%m")
    insertion = pg_insert(UsageCounter).values(
        user_id=user_id,
        period=periode,
        applications_count=0,
        llm_tokens_in=tokens_entree,
        llm_tokens_out=tokens_sortie,
        cost_usd=cout_usd,
    )
    await session.execute(
        insertion.on_conflict_do_update(
            constraint="uq_usage_counters_user_period",
            set_={
                "llm_tokens_in": UsageCounter.llm_tokens_in + insertion.excluded.llm_tokens_in,
                "llm_tokens_out": UsageCounter.llm_tokens_out + insertion.excluded.llm_tokens_out,
                "cost_usd": UsageCounter.cost_usd + insertion.excluded.cost_usd,
            },
        )
    )


async def _analyser_en_arriere_plan(
    user_id: int, texte: str | None, cle_image: str | None, type_image: str | None
) -> None:
    """Possède son propre client Redis et sa propre session.

    Le client de `deps.cache_redis` est fermé en fin de requête : le passer ici
    laisserait la tâche travailler sur une connexion morte — piège déjà payé en
    Phase 2 sur le rafraîchissement des offres.
    """
    settings = get_settings()
    client: aioredis.Redis = aioredis.from_url(settings.redis_url, decode_responses=False)
    try:
        image: bytes | None = None
        if cle_image is not None:
            lu = await client.get(cle_image)
            await client.delete(cle_image)
            # `decode_responses=False` : ce sont des octets, ou rien si le TTL
            # a expiré.
            image = lu if isinstance(lu, bytes) else None
            if image is None:
                # Le TTL a expiré avant qu'on consomme l'image. Pas de reprise à
                # écrire : l'utilisateur redépose.
                await _marquer_echec(user_id, "image_expiree")
                return

        profil, transcription, cout = await analyser_cv(
            texte=texte,
            image=image,
            type_image=type_image,
            # `modele` : garde contre une image envoyée à un modèle qui ne la lit
            # pas (DEEPSEEK_MODELE est configurable). La température vient de
            # `analyser_cv`, qui la tire de `TEMPERATURE_CV` : jamais en dur ici.
            modele=settings.deepseek_modele,
            appeler=lambda messages, temperature: appeler_deepseek(
                messages,
                modele=settings.deepseek_modele,
                cle_api=settings.deepseek_api_key.get_secret_value(),
                temperature=temperature,
            ),
        )
    except Exception as exc:  # noqa: BLE001 — une analyse ratée n'est pas une panne
        # Seul le NOM du type : le message d'une exception de cette chaîne peut
        # contenir un fragment de CV, et une alerte admin recopie son contexte
        # par le réseau (§7).
        # Un `ValueError` (garde de `analyser_cv`) est une erreur de
        # programmeur, par exemple un DEEPSEEK_MODELE mal réglé : son nom de
        # type la distingue d'une panne de DeepSeek dans le journal.
        code = getattr(exc, "code", None) or "analyse_echouee"
        # Deux appels payés ne doivent pas disparaître (`CvIllisible.cout`).
        cout_perdu = getattr(exc, "cout", None)
        log.error(
            "cv_analyse_echouee",
            user_id=user_id,
            type_erreur=type(exc).__name__,
            cout_usd=None if cout_perdu is None else str(cout_perdu),
        )
        await _marquer_echec(user_id, str(code), cout_perdu)
        return
    finally:
        await client.aclose()

    async with session_scope() as session:
        ligne = await _profil_de(session, user_id)
        if ligne is None:  # compte supprimé pendant l'analyse
            return
        ligne.raw_cv_text = transcription
        ligne.structured = profil
        ligne.parse_etat = "pret"
        ligne.parse_erreur = None
        await consigner_cout(
            session,
            user_id,
            tokens_entree=cout.tokens_entree_frais + cout.tokens_entree_cache,
            tokens_sortie=cout.tokens_sortie,
            cout_usd=cout.cout_usd,
        )
    log.info(
        "cv_analyse_terminee",
        user_id=user_id,
        tokens_entree=cout.tokens_entree_frais + cout.tokens_entree_cache,
        tokens_sortie=cout.tokens_sortie,
        cout_usd=str(cout.cout_usd),
    )


async def _marquer_echec(user_id: int, code: str, cout: Decimal | None = None) -> None:
    """`cout` : dollars déjà payés (deux appels après une relance ratée). Le
    cas le plus coûteux est aussi celui où l'argent disparaîtrait sans trace.
    Les tokens ne sont pas connus ici : seul le montant l'est."""
    async with session_scope() as session:
        ligne = await _profil_de(session, user_id)
        if ligne is not None:
            ligne.parse_etat = "echec"
            ligne.parse_erreur = code
        if isinstance(cout, Decimal) and cout > 0:
            await consigner_cout(
                session, user_id, tokens_entree=0, tokens_sortie=0, cout_usd=cout
            )


def _planifier(coro: Any) -> None:
    tache = asyncio.create_task(coro)
    _TACHES_DE_FOND.add(tache)
    tache.add_done_callback(_TACHES_DE_FOND.discard)


@router.post("/profil/cv", status_code=status.HTTP_202_ACCEPTED)
async def deposer_cv(
    response: Response,
    utilisateur: Annotated[User, Depends(deps.utilisateur_courant)],
    session: Annotated[AsyncSession, Depends(deps.session_db)],
    cache: Annotated[Any, Depends(deps.cache_redis)],
    settings: Annotated[Settings, Depends(deps.reglages)],
    fichier: Annotated[UploadFile, File()],
) -> ProfilVu:
    contenu = await fichier.read()
    if len(contenu) > settings.cv_taille_max_octets:
        raise CvTropGros

    type_cv = cv_fichier.reconnaitre_type(contenu)

    # Le plafond est consommé AVANT tout travail : extraire le texte puis
    # refuser serait du calcul payé pour rien.
    await autoriser_analyse_cv(
        cache,
        user_id=utilisateur.id,
        par_jour=settings.cv_analyses_par_jour,
        secret=cles.deriver(settings.jwt_secret.get_secret_value(), "limite"),
    )

    texte: str | None = None
    cle_image: str | None = None
    if cv_fichier.est_une_image(type_cv):
        # Une photo n'a pas de texte à extraire : elle doit survivre jusqu'à la
        # tâche de fond. Redis avec un TTL court — jamais le disque, jamais
        # Postgres, donc jamais une sauvegarde (spec §8).
        cle_image = f"{_PREFIXE_IMAGE}:{utilisateur.id}:{datetime.now(UTC).timestamp()}"
        await cache.set(cle_image, contenu, ex=settings.cv_image_ttl_secondes)
    else:
        texte = cv_fichier.extraire_texte(
            contenu, type_cv, minimum=settings.cv_texte_min_caracteres
        )

    profil = await _profil_de(session, utilisateur.id)
    if profil is None:
        profil = Profile(user_id=utilisateur.id)
        session.add(profil)
    profil.parse_etat = "en_cours"
    profil.parse_erreur = None
    profil.parse_demarre_le = datetime.now(UTC)
    await session.flush()

    _planifier(
        _analyser_en_arriere_plan(utilisateur.id, texte, cle_image, type_cv)
    )
    return _vue(profil)


@router.put("/profil")
async def corriger_profil(
    corps: CorrectionProfil,
    utilisateur: Annotated[User, Depends(deps.utilisateur_courant)],
    session: Annotated[AsyncSession, Depends(deps.session_db)],
) -> ProfilVu:
    """Corrections et préférences dans la même soumission : chaque étape coûte
    des abandons et un aller-retour payé en data (§11)."""
    profil = await _profil_de(session, utilisateur.id)
    if profil is None or profil.structured is None:
        raise ProfilAbsent

    structure = dict(profil.structured)
    for champ, valeur in corps.model_dump().items():
        structure[champ] = valeur
    profil.structured = structure
    return _vue(profil)
