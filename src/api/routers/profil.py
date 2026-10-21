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
from fastapi import APIRouter, Depends, File, UploadFile, status
from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.api import deps
from src.api.schemas.profil import CorrectionProfil, ProfilVu
from src.config import Settings, get_settings
from src.core import cv_fichier
from src.core.auth import cles
from src.core.cv_etat import etat_affiche
from src.core.cv_limites import autoriser_analyse_cv, liberer_analyse_cv
from src.core.erreurs import AnalyseIndisponible, CvTropGros, ErreurMetier, ProfilAbsent
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

# Plafond de simultanéité des analyses, tous utilisateurs confondus. Le plafond
# de `cv_limites.py` est par UTILISATEUR et par jour : il ne borne pas ce qui
# tourne EN MÊME TEMPS. Or une analyse de photo retient le fichier reçu (5 Mo au
# plus), son encodage base64 (~4/3 de plus) et les tampons du client HTTP
# pendant toute la durée de l'appel à DeepSeek — de l'ordre de 20 à 30 Mo chacune
# pendant plusieurs secondes. Sur la CX22 à 4 Go du brief, partagée avec
# Postgres, Redis et `web`, quelques dizaines de dépôts concurrents tuent `api`
# et emportent TOUTES les analyses en vol, quota consommé et argent déjà dépensé.
#
# 4 places et non 8 : 4 × 30 Mo ≈ 120 Mo de pointe, ce que la machine absorbe
# sans discuter, et le débit n'en souffre pas puisque l'essentiel du temps d'une
# analyse est passé à attendre DeepSeek, pas à calculer. Le dépôt, lui, répond
# toujours immédiatement : c'est la tâche de fond qui fait la queue.
#
# Variable de module (et non constante figée dans la fonction) pour qu'un test
# puisse la remplacer par un sémaphore à une place.
_PLACES_SIMULTANEES = 4
_SEMAPHORE = asyncio.Semaphore(_PLACES_SIMULTANEES)


def cle_image_cv(user_id: int) -> str:
    """Clé Redis de l'image d'un CV en attente d'analyse.

    Déterministe, sans horodatage : `DELETE /moi` doit pouvoir l'effacer en O(1)
    sans `SCAN`. Le prix de ce choix est qu'un utilisateur n'a qu'UNE case : un
    second dépôt écrase l'image du premier. La conséquence est bornée et toujours
    la même — l'un des deux dépôts finit en `image_expiree` et l'utilisateur
    redépose — mais ce n'est pas forcément le plus ancien qui perd : si la
    première tâche a déjà démarré son analyse, c'est elle qui lira l'image de la
    seconde, et la seconde ne trouvera plus rien. Seule la garde sur
    `parse_demarre_le` est exacte : le profil enregistré est toujours celui du
    dépôt le plus récent, quelle que soit l'image analysée.
    """
    return f"{_PREFIXE_IMAGE}:{user_id}"



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


def _ouvrir_redis() -> aioredis.Redis:
    """Client propre à la tâche de fond. `decode_responses=False` : l'image est
    binaire, la relire décodée la corromprait en tentant de l'interpréter en UTF-8.
    Isolé pour que les tests puissent le substituer."""
    client: aioredis.Redis = aioredis.from_url(get_settings().redis_url, decode_responses=False)
    return client


async def _analyser_en_arriere_plan(
    user_id: int,
    texte: str | None,
    cle_image: str | None,
    type_image: str | None,
    depose_le: datetime,
) -> None:
    """Possède son propre client Redis et sa propre session.

    Le client de `deps.cache_redis` est fermé en fin de requête : le passer ici
    laisserait la tâche travailler sur une connexion morte — piège déjà payé en
    Phase 2 sur le rafraîchissement des offres.

    Rien ne doit s'en échapper : une exception sortant d'ici tuerait la tâche sur
    « Task exception was never retrieved », et asyncio journalise alors la trace
    chaînée, message compris — or le message d'une erreur de base peut porter le
    contenu d'un CV.
    """
    try:
        await _analyser(user_id, texte, cle_image, type_image, depose_le)
    except Exception as exc:  # noqa: BLE001 — dernière barrière, nom du type seulement
        log.error("cv_tache_de_fond_echouee", user_id=user_id, type_erreur=type(exc).__name__)


async def _demarrer(user_id: int, depose_le: datetime) -> datetime | None:
    """Passe la ligne de `en_attente` à `en_cours`, et (re)pose son horloge.

    Rend le nouvel instant, qui devient le jeton de la garde optimiste pour la
    suite de l'analyse — ou `None` quand il n'y a plus rien à analyser.

    Deux raisons d'être, et la première est une question d'argent : un dépôt
    plus récent arrivé pendant l'attente a réécrit `parse_demarre_le`, donc le
    `UPDATE` ci-dessous ne touche aucune ligne, et on abandonne AVANT de payer
    un appel dont le résultat serait de toute façon jeté par la garde finale.
    La seconde est l'horloge de péremption (`core/cv_etat.py`) : si elle restait
    posée à l'instant du dépôt, le temps passé en file d'attente se déduirait du
    délai de l'analyse et un CV serait annoncé perdu avant d'avoir été lu.
    """
    debut = datetime.now(UTC)
    async with session_scope() as session:
        # `returning` plutôt que `rowcount` : la ligne rendue dit sans ambiguïté
        # que la promotion a eu lieu, et le type est exact pour mypy.
        promue = (
            await session.execute(
                update(Profile)
                .where(
                    Profile.user_id == user_id,
                    Profile.parse_demarre_le == depose_le,
                    Profile.parse_etat == "en_attente",
                )
                .values(parse_etat="en_cours", parse_demarre_le=debut)
                .returning(Profile.user_id)
            )
        ).scalar_one_or_none()
        if promue is None:
            return None
    return debut


async def _analyser(
    user_id: int,
    texte: str | None,
    cle_image: str | None,
    type_image: str | None,
    depose_le: datetime,
) -> None:
    """Attend une place, puis analyse. Le dépôt, lui, a déjà répondu."""
    async with _SEMAPHORE:
        demarre_le = await _demarrer(user_id, depose_le)
        if demarre_le is None:
            # Un dépôt plus récent a pris la main pendant l'attente (ou le
            # compte a disparu) : rien à payer, rien à écrire.
            log.info("cv_analyse_abandonnee", user_id=user_id)
            return
        await _analyser_sous_plafond(user_id, texte, cle_image, type_image, demarre_le)


async def _analyser_sous_plafond(
    user_id: int,
    texte: str | None,
    cle_image: str | None,
    type_image: str | None,
    demarre_le: datetime,
) -> None:
    settings = get_settings()
    client = _ouvrir_redis()
    try:
        image: bytes | None = None
        if cle_image is not None:
            lu = await client.get(cle_image)
            await client.delete(cle_image)
            image = lu if isinstance(lu, bytes) else None
            if image is None:
                # Le TTL a expiré avant qu'on consomme l'image. Pas de reprise à
                # écrire : l'utilisateur redépose.
                await _echec_sans_fuite(user_id, "image_expiree", None, demarre_le)
                return

        try:
            profil, transcription, cout = await analyser_cv(
                texte=texte,
                image=image,
                type_image=type_image,
                # `modele` : garde contre une image envoyée à un modèle qui ne la
                # lit pas (DEEPSEEK_MODELE est configurable). La température vient
                # de `analyser_cv` (`TEMPERATURE_CV`) : jamais en dur ici.
                modele=settings.deepseek_modele,
                appeler=lambda messages, temperature: appeler_deepseek(
                    messages,
                    modele=settings.deepseek_modele,
                    cle_api=settings.deepseek_api_key.get_secret_value(),
                    temperature=temperature,
                ),
            )
        except Exception as exc:  # noqa: BLE001 — une analyse ratée n'est pas une panne
            # Seul le NOM du type : le message peut contenir un fragment de CV, et
            # une alerte admin recopie son contexte par le réseau (§7). Un
            # `ValueError` (garde de `analyser_cv`) est une erreur de
            # programmeur, par exemple un DEEPSEEK_MODELE mal réglé : son nom la
            # distingue d'une panne de DeepSeek.
            # `ErreurMetier` seulement : `openai.APIError` porte aussi un `.code`,
            # qui n'a rien à faire dans un VARCHAR(64) lu par le client web.
            code = exc.code if isinstance(exc, ErreurMetier) else "analyse_echouee"
            # Deux appels payés ne doivent pas disparaître (`CvIllisible.cout`).
            cout_perdu = getattr(exc, "cout", None)
            log.error(
                "cv_analyse_echouee",
                user_id=user_id,
                type_erreur=type(exc).__name__,
                cout_usd=None if cout_perdu is None else str(cout_perdu),
            )
            if isinstance(exc, AnalyseIndisponible):
                # L'utilisateur n'a RIEN reçu : sa place lui est rendue (§9). Un
                # échec qui lui a rendu un résultat inutilisable, lui, garde sa
                # place consommée (`CvIllisible`). Rendre la place et consigner
                # la dépense sont deux décisions indépendantes : une première
                # tentative facturée avant la panne voyage dans `cout` et part
                # quand même dans `usage_counters`, juste en dessous.
                await _liberer_sans_fuite(client, user_id, settings)
            await _echec_sans_fuite(user_id, code, cout_perdu, demarre_le)
            return
    finally:
        await client.aclose()

    async with session_scope() as session:
        # Le coût est dû même si le résultat est périmé : l'appel a été payé.
        await consigner_cout(
            session,
            user_id,
            tokens_entree=cout.tokens_entree_frais + cout.tokens_entree_cache,
            tokens_sortie=cout.tokens_sortie,
            cout_usd=cout.cout_usd,
        )
        ligne = await _profil_de(session, user_id)
        # Garde optimiste : si un dépôt plus récent a changé `parse_demarre_le`,
        # le gagnant ne doit pas être celui qui FINIT en dernier, mais celui qui
        # a DÉPOSÉ en dernier. Sinon le profil de l'ancien CV écraserait le neuf.
        if ligne is not None and ligne.parse_demarre_le == demarre_le:
            ligne.raw_cv_text = transcription
            ligne.structured = profil
            ligne.parse_etat = "pret"
            ligne.parse_erreur = None
    log.info(
        "cv_analyse_terminee",
        user_id=user_id,
        tokens_entree=cout.tokens_entree_frais + cout.tokens_entree_cache,
        tokens_sortie=cout.tokens_sortie,
        cout_usd=str(cout.cout_usd),
    )


async def _liberer_sans_fuite(client: aioredis.Redis, user_id: int, settings: Settings) -> None:
    try:
        await liberer_analyse_cv(
            client,
            user_id=user_id,
            secret=cles.deriver(settings.jwt_secret.get_secret_value(), "limite"),
        )
    except Exception as exc:  # noqa: BLE001 — jamais de chaînage vers l'original
        log.error("cv_liberation_quota_echouee", user_id=user_id, type_erreur=type(exc).__name__)


async def _echec_sans_fuite(
    user_id: int, code: str, cout: Decimal | None, demarre_le: datetime
) -> None:
    """Appelée depuis un bloc `except` : sans son propre garde, une exception de
    la base sortirait avec `__context__` = l'exception d'origine."""
    try:
        await _marquer_echec(user_id, code, cout, demarre_le)
    except Exception as exc:  # noqa: BLE001 — nom du type seulement
        log.error("cv_marquage_echec_echoue", user_id=user_id, type_erreur=type(exc).__name__)


async def _marquer_echec(
    user_id: int, code: str, cout: Decimal | None = None, demarre_le: datetime | None = None
) -> None:
    """`cout` : dollars déjà payés quand l'analyse a échoué — deux appels après
    une relance ratée, ou un appel facturé suivi d'une panne. Dans les deux cas,
    c'est l'argent qui disparaîtrait sans trace. Les tokens ne sont pas connus
    ici : seul le montant l'est.

    `demarre_le` : même garde optimiste que le succès — l'échec d'un ancien dépôt
    ne doit pas écraser l'analyse en cours d'un dépôt plus récent."""
    async with session_scope() as session:
        ligne = await _profil_de(session, user_id)
        if ligne is not None and (demarre_le is None or ligne.parse_demarre_le == demarre_le):
            ligne.parse_etat = "echec"
            ligne.parse_erreur = code
        if isinstance(cout, Decimal) and cout > 0:
            await consigner_cout(session, user_id, tokens_entree=0, tokens_sortie=0, cout_usd=cout)


async def preparer_profil(session: AsyncSession, user_id: int, depose_le: datetime) -> Profile:
    """Pose le profil en `en_attente` par un upsert atomique.

    `en_attente` et non `en_cours` : rien n'est en cours tant que la tâche de
    fond n'a pas obtenu une place (`_SEMAPHORE`). L'écran distingue les deux et
    le dit, et chaque phase a sa propre horloge de péremption
    (`core/cv_etat.py`).

    Lire puis insérer laisserait deux dépôts simultanés (le double-tap sur un
    bouton lent en 3G) s'insérer tous deux : le second violerait l'unicité de
    `profiles.user_id`. Le contenu précédent (`structured`) est conservé jusqu'à
    la fin de la nouvelle analyse.
    """
    insertion = pg_insert(Profile).values(
        user_id=user_id, parse_etat="en_attente", parse_erreur=None, parse_demarre_le=depose_le
    )
    await session.execute(
        insertion.on_conflict_do_update(
            index_elements=["user_id"],
            set_={
                "parse_etat": "en_attente",
                "parse_erreur": None,
                "parse_demarre_le": depose_le,
            },
        )
    )
    # `populate_existing` : l'objet peut déjà être dans la session avec les
    # valeurs d'avant l'upsert.
    requete = (
        select(Profile).where(Profile.user_id == user_id).execution_options(populate_existing=True)
    )
    return (await session.execute(requete)).scalar_one()


def _planifier(coro: Any) -> None:
    tache = asyncio.create_task(coro)
    _TACHES_DE_FOND.add(tache)
    tache.add_done_callback(_TACHES_DE_FOND.discard)


@router.post("/profil/cv", status_code=status.HTTP_202_ACCEPTED)
async def deposer_cv(
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
        # tâche de fond. Redis avec un TTL court, jamais Postgres, donc jamais une
        # sauvegarde (spec §8). Le disque n'est pas touché non plus : le fichier
        # reçu reste en mémoire parce que `spool_max_size` est relevé au plafond
        # du CV (cf. `create_app`).
        cle_image = cle_image_cv(utilisateur.id)
        await cache.set(cle_image, contenu, ex=settings.cv_image_ttl_secondes)
    else:
        texte = cv_fichier.extraire_texte(
            contenu, type_cv, minimum=settings.cv_texte_min_caracteres
        )

    depose_le = datetime.now(UTC)
    profil = await preparer_profil(session, utilisateur.id, depose_le)
    # Valider AVANT de planifier la tâche : elle ouvre sa propre session, et une
    # ligne encore invisible pour elle lui ferait jeter son résultat en silence
    # (son `UPDATE` de démarrage ne trouverait rien à promouvoir). `session_scope`
    # valide une transaction déjà vide sans rien faire : ce commit anticipé ne
    # retire rien au commit de fin de requête.
    await session.commit()

    _planifier(_analyser_en_arriere_plan(utilisateur.id, texte, cle_image, type_cv, depose_le))
    return _vue(profil)


@router.put("/profil")
async def corriger_profil(
    corps: CorrectionProfil,
    utilisateur: Annotated[User, Depends(deps.utilisateur_courant)],
    session: Annotated[AsyncSession, Depends(deps.session_db)],
    settings: Annotated[Settings, Depends(deps.reglages)],
) -> ProfilVu:
    """Corrections et préférences dans la même soumission : chaque étape coûte
    des abandons et un aller-retour payé en data (§11).

    Un enregistrement réussi remet l'état à `pret` et efface `parse_erreur` :
    sans cela, un redépôt raté laissait « Nous n'avons pas réussi à lire ce
    CV… » en rouge sur `/profil` POUR TOUJOURS, y compris après que
    l'utilisateur a réparé son profil à la main. Annoncer en permanence un
    échec à quelqu'un qui vient de corriger est une affirmation fausse, sur
    l'écran central du produit.

    La remise à `pret` ne court-circuite PAS la garde optimiste : elle n'a lieu
    que si l'état AFFICHÉ n'est plus en vol. On passe par `etat_affiche`, et
    non par `parse_etat` brut, pour les deux raisons symétriques :
    - une analyse réellement en vol (`en_attente`/`en_cours`, horloge encore
      fraîche) garde son état : elle finira et écrira son résultat sous sa
      propre garde `parse_demarre_le`. Lui coller un `pret` ferait clignoter
      l'écran entre deux vérités ;
    - une analyse `en_cours` PÉRIMÉE est déjà présentée comme un échec par
      `GET /profil`. Sans ce passage par la même règle, son bandeau serait
      resté lui aussi définitif — le défaut corrigé ici, par une autre porte.
    """
    profil = await _profil_de(session, utilisateur.id)
    if profil is None or profil.structured is None:
        raise ProfilAbsent

    structure = dict(profil.structured)
    # `exclude_unset` : un champ omis par le client reste tel quel ; sans lui,
    # omettre `competences` les viderait. Les champs que ce schéma ignore
    # (`telephone`, `pretention_salariale`, expériences...) survivent pareil.
    for champ, valeur in corps.model_dump(exclude_unset=True).items():
        structure[champ] = valeur
    profil.structured = structure

    etat, _erreur = etat_affiche(
        profil.parse_etat,
        profil.parse_demarre_le,
        profil.parse_erreur,
        maintenant=datetime.now(UTC),
        delai_max_secondes=settings.cv_analyse_delai_max_secondes,
    )
    if etat not in ("en_attente", "en_cours"):
        profil.parse_etat = "pret"
        profil.parse_erreur = None
    return _vue(profil)
