"""POST /profil/cv, GET /profil, PUT /profil (spec §7)."""

from __future__ import annotations

import io
from collections.abc import AsyncIterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tests.conftest import FournisseurCourrielEspion, demander_code_verification

ADRESSE = "profil@jobbot-test.sn"
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 128


def _docx(texte: str) -> bytes:
    from docx import Document

    doc = Document()
    doc.add_paragraph(texte)
    tampon = io.BytesIO()
    doc.save(tampon)
    return tampon.getvalue()


def _connecter(client: TestClient, espion: FournisseurCourrielEspion) -> None:
    code = demander_code_verification(client, espion, ADRESSE)
    assert client.post(
        "/auth/code/verifie",
        json={"email": ADRESSE, "code": code, "nom_complet": "Awa"},
    ).status_code == 200


@pytest.mark.integration
def test_profil_sans_cookie_refuse(client_auth: TestClient) -> None:
    assert client_auth.get("/profil").status_code == 401
    assert client_auth.post("/profil/cv", files={"fichier": ("cv.pdf", b"%PDF")}).status_code == 401


@pytest.mark.integration
def test_profil_vide_au_depart(
    client_auth: TestClient, fournisseur_courriel_espion: FournisseurCourrielEspion
) -> None:
    _connecter(client_auth, fournisseur_courriel_espion)
    corps = client_auth.get("/profil").json()
    assert corps["etat"] == "absent"
    assert corps["structured"] is None


@pytest.mark.integration
def test_un_type_refuse_ne_cree_aucun_profil(
    client_auth: TestClient, fournisseur_courriel_espion: FournisseurCourrielEspion
) -> None:
    _connecter(client_auth, fournisseur_courriel_espion)
    r = client_auth.post("/profil/cv", files={"fichier": ("cv.pdf", b"MZ\x90\x00 pas un pdf")})
    assert r.status_code == 415
    assert r.json()["erreur"] == "cv_type_refuse"
    assert client_auth.get("/profil").json()["etat"] == "absent"


@pytest.mark.integration
def test_un_document_sans_texte_est_refuse_sans_appel_llm(
    client_auth: TestClient, fournisseur_courriel_espion: FournisseurCourrielEspion
) -> None:
    """Le cas du PDF scanné : refusé dans la requête, sans rien payer."""
    _connecter(client_auth, fournisseur_courriel_espion)
    r = client_auth.post("/profil/cv", files={"fichier": ("cv.docx", _docx("abc"))})
    assert r.status_code == 422
    assert r.json()["erreur"] == "cv_sans_texte"


@pytest.mark.integration
def test_un_fichier_trop_gros_est_refuse(
    client_auth: TestClient, fournisseur_courriel_espion: FournisseurCourrielEspion
) -> None:
    _connecter(client_auth, fournisseur_courriel_espion)
    enorme = b"%PDF" + b"\x00" * (6 * 1024 * 1024)
    r = client_auth.post("/profil/cv", files={"fichier": ("cv.pdf", enorme)})
    assert r.status_code == 413
    assert r.json()["erreur"] == "cv_trop_gros"


@pytest.mark.integration
def test_un_depot_valide_passe_en_attente_et_rend_202(
    client_auth: TestClient, fournisseur_courriel_espion: FournisseurCourrielEspion
) -> None:
    """La réponse ne doit JAMAIS attendre l'analyse : l'utilisateur est sur 3G.

    `en_attente` et non `en_cours` : rien n'est en cours tant que la tâche de
    fond n'a pas obtenu une place (plafond de simultanéité, I-1)."""
    _connecter(client_auth, fournisseur_courriel_espion)
    contenu = _docx("Awa Diop comptable chez Alpha SARL depuis 2019. " * 20)
    r = client_auth.post("/profil/cv", files={"fichier": ("cv.docx", contenu)})
    assert r.status_code == 202
    assert r.json()["etat"] == "en_attente"


@pytest.mark.integration
def test_le_plafond_journalier_sapplique(
    client_auth: TestClient, fournisseur_courriel_espion: FournisseurCourrielEspion
) -> None:
    _connecter(client_auth, fournisseur_courriel_espion)
    contenu = _docx("Awa Diop comptable chez Alpha SARL depuis 2019. " * 20)
    codes = [
        client_auth.post("/profil/cv", files={"fichier": ("cv.docx", contenu)}).status_code
        for _ in range(7)
    ]
    assert 429 in codes, "le plafond CV_ANALYSES_PAR_JOUR doit finir par refuser"


@pytest.mark.integration
def test_corriger_sans_profil_est_refuse(
    client_auth: TestClient, fournisseur_courriel_espion: FournisseurCourrielEspion
) -> None:
    _connecter(client_auth, fournisseur_courriel_espion)
    r = client_auth.put("/profil", json={"nom_complet": "Awa Diop", "competences": []})
    assert r.status_code == 409
    assert r.json()["erreur"] == "profil_absent"


@pytest.mark.integration
async def test_le_cout_sajoute_au_compteur_du_mois(
    client_auth: TestClient,
    fournisseur_courriel_espion: FournisseurCourrielEspion,
    base_profils_test: async_sessionmaker[AsyncSession],
) -> None:
    """Un upsert qui additionne : la seconde analyse ne remplace pas la première."""
    from datetime import UTC, datetime
    from decimal import Decimal

    from sqlalchemy import select

    from src.api.routers.profil import consigner_cout
    from src.db.models import UsageCounter, User

    _connecter(client_auth, fournisseur_courriel_espion)
    async with base_profils_test() as s:
        uid = (await s.execute(select(User.id).where(User.email == ADRESSE))).scalar_one()
        await consigner_cout(
            s, uid, tokens_entree=100, tokens_sortie=10, cout_usd=Decimal("0.000123")
        )
        await s.commit()
    async with base_profils_test() as s:
        await consigner_cout(
            s, uid, tokens_entree=50, tokens_sortie=5, cout_usd=Decimal("0.000200")
        )
        await s.commit()
    async with base_profils_test() as s:
        lignes = (
            (await s.execute(select(UsageCounter).where(UsageCounter.user_id == uid)))
            .scalars()
            .all()
        )
    assert len(lignes) == 1
    assert lignes[0].period == datetime.now(UTC).strftime("%Y-%m")
    assert (lignes[0].llm_tokens_in, lignes[0].llm_tokens_out) == (150, 15)
    assert lignes[0].cost_usd == Decimal("0.000323")


@pytest.mark.integration
async def test_un_echec_apres_relance_consigne_son_cout(
    client_auth: TestClient,
    fournisseur_courriel_espion: FournisseurCourrielEspion,
    base_profils_test: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Le cas le plus coûteux (deux appels payés, rien d'exploitable) ne doit
    pas disparaître du suivi de marge."""
    from contextlib import asynccontextmanager
    from decimal import Decimal

    from sqlalchemy import select

    from src.api.routers import profil as routeur
    from src.db.models import UsageCounter, User

    @asynccontextmanager
    async def _scope() -> AsyncIterator[AsyncSession]:
        async with base_profils_test() as s:
            yield s
            await s.commit()

    monkeypatch.setattr(routeur, "session_scope", _scope)
    _connecter(client_auth, fournisseur_courriel_espion)
    async with base_profils_test() as s:
        uid = (await s.execute(select(User.id).where(User.email == ADRESSE))).scalar_one()
    await routeur._marquer_echec(uid, "cv_illisible", Decimal("0.004"))
    async with base_profils_test() as s:
        ligne = (
            await s.execute(select(UsageCounter).where(UsageCounter.user_id == uid))
        ).scalar_one()
    assert ligne.cost_usd == Decimal("0.004")


# --- Harnais de la tâche de fond -------------------------------------------
#
# `client_auth` remplace `deps.cache_redis` par un `FauxCache`, mais la tâche de
# fond ouvre SON client. Sans ce harnais, l'image écrite par la route n'est
# jamais là où la tâche la cherche : tout le chemin photo restait non vérifié.


class _ClientPartage:
    """Client de la tâche de fond, branché sur le MÊME `FauxCache` que la route."""

    def __init__(self, cache: Any) -> None:
        self._cache = cache
        self.ttl_vus: dict[str, int | None] = {}

    async def get(self, name: str) -> Any:
        self.ttl_vus[name] = self._cache.ttl.get(name)
        return await self._cache.get(name)

    async def delete(self, *names: str) -> Any:
        return await self._cache.delete(*names)

    async def incr(self, name: str) -> int:
        return await self._cache.incr(name)

    async def decr(self, name: str) -> int:
        return await self._cache.decr(name)

    async def aclose(self) -> None:
        return None


class _Analyse:
    """Double de `analyser_cv` : jamais de réseau, jamais de DeepSeek."""

    def __init__(self) -> None:
        self.appels: list[dict[str, Any]] = []
        self.exception: Exception | None = None

    async def __call__(self, **kw: Any) -> Any:
        from decimal import Decimal

        from src.llm.client import CoutAppel

        self.appels.append(kw)
        if self.exception is not None:
            raise self.exception
        profil = {"nom_complet": "Awa Diop", "competences": ["Excel"], "telephone": "770000000"}
        return profil, "transcription", CoutAppel(10, 5, 3, Decimal("0.0001"))


class _Harnais:
    def __init__(self, analyse: _Analyse, client: _ClientPartage, cache: Any) -> None:
        self.analyse = analyse
        self.client = client
        self.cache = cache


@pytest.fixture
def harnais(
    monkeypatch: pytest.MonkeyPatch,
    faux_cache: Any,
    base_profils_test: async_sessionmaker[AsyncSession],
) -> _Harnais:
    from contextlib import asynccontextmanager

    from src.api.routers import profil as routeur

    analyse = _Analyse()
    client = _ClientPartage(faux_cache)

    @asynccontextmanager
    async def _scope() -> AsyncIterator[AsyncSession]:
        async with base_profils_test() as s:
            yield s
            await s.commit()

    monkeypatch.setattr(routeur, "analyser_cv", analyse)
    monkeypatch.setattr(routeur, "_ouvrir_redis", lambda: client)
    monkeypatch.setattr(routeur, "session_scope", _scope)
    return _Harnais(analyse, client, faux_cache)


def _attendre_fin(client: TestClient) -> dict[str, Any]:
    import time

    for _ in range(100):
        corps: dict[str, Any] = client.get("/profil").json()
        # `en_attente` compte comme « pas fini » : sinon le premier sondage
        # rendrait l'état de la file d'attente et le test ne prouverait rien.
        if corps["etat"] not in ("en_attente", "en_cours"):
            return corps
        time.sleep(0.05)
    raise AssertionError("l'analyse ne s'est pas terminée")


async def _uid(base: async_sessionmaker[AsyncSession]) -> int:
    from sqlalchemy import select

    from src.db.models import User

    async with base() as s:
        return (await s.execute(select(User.id).where(User.email == ADRESSE))).scalar_one()


def _cles(cache: Any, prefixe: str) -> list[str]:
    return [k for k in cache.valeurs if k.startswith(prefixe)]


@pytest.mark.integration
def test_une_photo_traverse_redis_et_ressort_en_pret(
    client_auth: TestClient,
    fournisseur_courriel_espion: FournisseurCourrielEspion,
    harnais: _Harnais,
) -> None:
    """Aller-retour de l'image : écrite par la route, lue en octets par la tâche,
    supprimée après lecture, avec son TTL posé au dépôt."""
    _connecter(client_auth, fournisseur_courriel_espion)
    r = client_auth.post("/profil/cv", files={"fichier": ("photo.jpg", JPEG)})
    assert r.status_code == 202
    assert _attendre_fin(client_auth)["etat"] == "pret"
    assert len(harnais.analyse.appels) == 1
    appel = harnais.analyse.appels[0]
    assert appel["image"] == JPEG
    assert appel["type_image"] == "jpeg"
    assert appel["texte"] is None
    assert _cles(harnais.cache, "jobbot:cv:image") == []
    (ttl,) = harnais.client.ttl_vus.values()
    assert ttl == 600


@pytest.mark.integration
async def test_une_image_dont_le_ttl_a_expire_echoue_sans_appel(
    client_auth: TestClient,
    fournisseur_courriel_espion: FournisseurCourrielEspion,
    harnais: _Harnais,
    base_profils_test: async_sessionmaker[AsyncSession],
) -> None:
    from datetime import UTC, datetime

    from sqlalchemy import select

    from src.api.routers import profil as routeur
    from src.db.models import Profile

    _connecter(client_auth, fournisseur_courriel_espion)
    uid = await _uid(base_profils_test)
    t = datetime.now(UTC)
    async with base_profils_test() as s:
        await routeur.preparer_profil(s, uid, t)
        await s.commit()
    await routeur._analyser_en_arriere_plan(uid, None, "jobbot:cv:image:expiree", "jpeg", t)
    async with base_profils_test() as s:
        ligne = (await s.execute(select(Profile).where(Profile.user_id == uid))).scalar_one()
    assert (ligne.parse_etat, ligne.parse_erreur) == ("echec", "image_expiree")
    assert harnais.analyse.appels == []


def _place_du_jour(cache: Any) -> int:
    (cle,) = _cles(cache, "jobbot:cv:analyses")
    return int(cache.valeurs[cle])


@pytest.mark.integration
def test_deepseek_injoignable_rend_la_place_du_quota(
    client_auth: TestClient,
    fournisseur_courriel_espion: FournisseurCourrielEspion,
    harnais: _Harnais,
) -> None:
    from src.core.erreurs import AnalyseIndisponible

    harnais.analyse.exception = AnalyseIndisponible()
    _connecter(client_auth, fournisseur_courriel_espion)
    client_auth.post("/profil/cv", files={"fichier": ("photo.jpg", JPEG)})
    corps = _attendre_fin(client_auth)
    assert (corps["etat"], corps["erreur"]) == ("echec", "analyse_indisponible")
    assert _place_du_jour(harnais.cache) == 0


@pytest.mark.integration
def test_une_analyse_payee_puis_illisible_garde_sa_place(
    client_auth: TestClient,
    fournisseur_courriel_espion: FournisseurCourrielEspion,
    harnais: _Harnais,
) -> None:
    from decimal import Decimal

    from src.core.erreurs import CvIllisible

    harnais.analyse.exception = CvIllisible(Decimal("0.002"))
    _connecter(client_auth, fournisseur_courriel_espion)
    client_auth.post("/profil/cv", files={"fichier": ("photo.jpg", JPEG)})
    corps = _attendre_fin(client_auth)
    assert (corps["etat"], corps["erreur"]) == ("echec", "cv_illisible")
    assert _place_du_jour(harnais.cache) == 1


@pytest.mark.integration
def test_le_code_dune_exception_tierce_nentre_pas_en_base(
    client_auth: TestClient,
    fournisseur_courriel_espion: FournisseurCourrielEspion,
    harnais: _Harnais,
) -> None:
    """`openai.APIError` porte un `.code` : il ne doit pas finir dans `parse_erreur`."""

    class ErreurTierce(Exception):
        code = "x" * 100

    harnais.analyse.exception = ErreurTierce()
    _connecter(client_auth, fournisseur_courriel_espion)
    client_auth.post("/profil/cv", files={"fichier": ("photo.jpg", JPEG)})
    corps = _attendre_fin(client_auth)
    assert corps["erreur"] == "analyse_echouee"


@pytest.mark.integration
async def test_deux_insertions_simultanees_ne_laissent_quune_ligne(
    client_auth: TestClient,
    fournisseur_courriel_espion: FournisseurCourrielEspion,
    base_profils_test: async_sessionmaker[AsyncSession],
) -> None:
    """Le double-tap : deux dépôts lisent « pas de profil » en même temps. Avec un
    SELECT puis INSERT, le second violerait `profiles.user_id` (500)."""
    import asyncio
    from datetime import UTC, datetime

    from sqlalchemy import func, select

    from src.api.routers import profil as routeur
    from src.db.models import Profile

    _connecter(client_auth, fournisseur_courriel_espion)
    uid = await _uid(base_profils_test)

    async def _depot() -> None:
        async with base_profils_test() as s:
            await routeur.preparer_profil(s, uid, datetime.now(UTC))
            await s.commit()

    await asyncio.gather(*[_depot() for _ in range(5)])
    async with base_profils_test() as s:
        n = (
            await s.execute(select(func.count()).select_from(Profile).where(Profile.user_id == uid))
        ).scalar_one()
    assert n == 1


@pytest.mark.integration
async def test_le_dernier_depot_gagne_meme_si_lancien_finit_apres(
    client_auth: TestClient,
    fournisseur_courriel_espion: FournisseurCourrielEspion,
    harnais: _Harnais,
    base_profils_test: async_sessionmaker[AsyncSession],
) -> None:
    from datetime import UTC, datetime, timedelta

    from sqlalchemy import select

    from src.api.routers import profil as routeur
    from src.db.models import Profile, UsageCounter

    _connecter(client_auth, fournisseur_courriel_espion)
    uid = await _uid(base_profils_test)
    ancien = datetime.now(UTC)
    recent = ancien + timedelta(seconds=1)
    async with base_profils_test() as s:
        await routeur.preparer_profil(s, uid, ancien)
        await s.commit()
    async with base_profils_test() as s:
        await routeur.preparer_profil(s, uid, recent)
        await s.commit()

    # L'ANCIEN dépôt n'a pas encore obtenu sa place : il doit abandonner AVANT
    # de payer, puisque son résultat serait de toute façon jeté (I-1, `_demarrer`).
    await routeur._analyser_en_arriere_plan(uid, "ancien cv", None, None, ancien)
    async with base_profils_test() as s:
        ligne = (await s.execute(select(Profile).where(Profile.user_id == uid))).scalar_one()
        compteurs = (
            (await s.execute(select(UsageCounter).where(UsageCounter.user_id == uid)))
            .scalars()
            .all()
        )
    assert ligne.parse_etat == "en_attente"
    assert ligne.parse_demarre_le == recent
    assert ligne.structured is None
    assert harnais.analyse.appels == [], "l'ancien dépôt ne doit RIEN payer"
    assert compteurs == []

    await routeur._analyser_en_arriere_plan(uid, "nouveau cv", None, None, recent)
    async with base_profils_test() as s:
        ligne = (await s.execute(select(Profile).where(Profile.user_id == uid))).scalar_one()
    assert ligne.parse_etat == "pret"
    assert ligne.structured is not None


@pytest.mark.integration
async def test_un_depot_arrive_pendant_lanalyse_nest_pas_ecrase_mais_le_cout_reste(
    client_auth: TestClient,
    fournisseur_courriel_espion: FournisseurCourrielEspion,
    harnais: _Harnais,
    base_profils_test: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """L'autre moitié de la garde optimiste : ici l'analyse a DÉJÀ démarré quand
    le second dépôt arrive. Trop tard pour abandonner, l'appel est payé — son
    résultat est jeté (le profil du vieux CV n'écrase pas le neuf), mais son coût
    reste consigné."""
    from datetime import UTC, datetime, timedelta

    from sqlalchemy import select

    from src.api.routers import profil as routeur
    from src.db.models import Profile, UsageCounter

    _connecter(client_auth, fournisseur_courriel_espion)
    uid = await _uid(base_profils_test)
    ancien = datetime.now(UTC)
    recent = ancien + timedelta(seconds=1)
    async with base_profils_test() as s:
        await routeur.preparer_profil(s, uid, ancien)
        await s.commit()

    reel = harnais.analyse

    async def _depot_concurrent(**kw: Any) -> Any:
        # Le second dépôt tombe PENDANT l'appel au modèle, comme en production.
        async with base_profils_test() as s:
            await routeur.preparer_profil(s, uid, recent)
            await s.commit()
        return await reel(**kw)

    # Sur l'objet du module : réaffecter `__call__` sur l'INSTANCE ne change
    # rien, Python résout les méthodes spéciales sur le type.
    monkeypatch.setattr(routeur, "analyser_cv", _depot_concurrent)
    await routeur._analyser_en_arriere_plan(uid, "ancien cv", None, None, ancien)

    async with base_profils_test() as s:
        ligne = (await s.execute(select(Profile).where(Profile.user_id == uid))).scalar_one()
        cout = (
            await s.execute(select(UsageCounter).where(UsageCounter.user_id == uid))
        ).scalar_one()
    assert ligne.parse_etat == "en_attente"
    assert ligne.parse_demarre_le == recent
    assert ligne.structured is None
    # ... mais son coût, lui, a bien été payé.
    assert cout.llm_tokens_in == 15


@pytest.mark.integration
async def test_une_panne_de_base_ne_senchaine_pas_a_lerreur_dorigine(
    client_auth: TestClient,
    fournisseur_courriel_espion: FournisseurCourrielEspion,
    harnais: _Harnais,
    base_profils_test: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from contextlib import asynccontextmanager
    from datetime import UTC, datetime

    from src.api.routers import profil as routeur
    from src.core.erreurs import CvIllisible

    @asynccontextmanager
    async def _casse() -> AsyncIterator[AsyncSession]:
        raise RuntimeError("fragment-de-cv-secret")
        yield  # pragma: no cover

    harnais.analyse.exception = CvIllisible()
    monkeypatch.setattr(routeur, "session_scope", _casse)
    _connecter(client_auth, fournisseur_courriel_espion)
    uid = await _uid(base_profils_test)
    # Ne doit rien lever : la tâche n'a pas à mourir sur « never retrieved ».
    await routeur._analyser_en_arriere_plan(uid, "texte", None, None, datetime.now(UTC))
    sortie = capsys.readouterr()
    assert "fragment-de-cv-secret" not in sortie.out + sortie.err


@pytest.mark.integration
def test_corriger_change_un_champ_et_conserve_les_autres(
    client_auth: TestClient,
    fournisseur_courriel_espion: FournisseurCourrielEspion,
    base_profils_test: async_sessionmaker[AsyncSession],
) -> None:
    """`exclude_unset` : un champ omis reste ; `telephone` et `pretention_salariale`,
    absents du schéma de correction, survivent."""
    import asyncio

    from src.db.models import Profile

    _connecter(client_auth, fournisseur_courriel_espion)

    async def _semer() -> None:
        uid = await _uid(base_profils_test)
        async with base_profils_test() as s:
            s.add(
                Profile(
                    user_id=uid,
                    parse_etat="pret",
                    structured={
                        "nom_complet": "Awa Diop",
                        "titre": "Comptable",
                        "competences": ["Sage"],
                        "telephone": "770000000",
                        "pretention_salariale": "300000",
                    },
                )
            )
            await s.commit()

    asyncio.run(_semer())
    r = client_auth.put("/profil", json={"titre": "Chef comptable", "competences": ["Excel"]})
    assert r.status_code == 200
    structure = client_auth.get("/profil").json()["structured"]
    assert structure["titre"] == "Chef comptable"
    assert structure["competences"] == ["Excel"]
    assert structure["nom_complet"] == "Awa Diop"  # omis : conservé
    assert structure["telephone"] == "770000000"
    assert structure["pretention_salariale"] == "300000"


def test_un_fichier_accepte_reste_en_memoire() -> None:
    """Au-delà de `spool_max_size`, Starlette écrit sur disque ; un CV plafonné à
    5 Mo ne doit jamais y toucher (spec §8)."""
    from starlette.formparsers import MultiPartParser

    from src.api.app import create_app
    from src.config import get_settings

    create_app()
    assert MultiPartParser.spool_max_size >= get_settings().cv_taille_max_octets


@pytest.mark.integration
async def test_le_plafond_de_simultaneite_borne_les_analyses_en_vol(
    base_profils_test: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """IMPORTANT I-1 : le plafond de `cv_limites.py` est par utilisateur et par
    jour — il ne borne pas ce qui tourne EN MÊME TEMPS. Sans `_SEMAPHORE`, N
    dépôts concurrents retiennent chacun 20 à 30 Mo et tuent `api` sur la CX22.

    N+2 analyses lancées d'un coup, un double qui bloque dans la partie
    coûteuse : au plus N doivent y être entrées à la fois.
    """
    import asyncio
    from contextlib import asynccontextmanager
    from datetime import UTC, datetime
    from decimal import Decimal

    from src.api.routers import profil as routeur
    from src.db.models import User
    from src.llm.client import CoutAppel

    places = 2
    monkeypatch.setattr(routeur, "_SEMAPHORE", asyncio.Semaphore(places))

    dedans = 0
    maximum = 0
    liberer = asyncio.Event()

    async def _analyse(**kw: Any) -> Any:
        nonlocal dedans, maximum
        dedans += 1
        maximum = max(maximum, dedans)
        await liberer.wait()
        dedans -= 1
        return {"nom_complet": "Awa"}, "transcription", CoutAppel(1, 1, 1, Decimal("0.0001"))

    class _Redis:
        async def aclose(self) -> None:
            return None

    @asynccontextmanager
    async def _scope() -> AsyncIterator[AsyncSession]:
        async with base_profils_test() as s:
            yield s
            await s.commit()

    monkeypatch.setattr(routeur, "analyser_cv", _analyse)
    monkeypatch.setattr(routeur, "_ouvrir_redis", lambda: _Redis())
    monkeypatch.setattr(routeur, "session_scope", _scope)

    # Des utilisateurs DISTINCTS : c'est la simultanéité ENTRE comptes que rien
    # d'autre ne borne. Purgés par `base_utilisateurs_test` (@jobbot-test.sn).
    depots: list[tuple[int, datetime]] = []
    async with base_profils_test() as s:
        for i in range(places + 2):
            compte = User(email=f"simultane{i}@jobbot-test.sn", full_name="Awa")
            s.add(compte)
            await s.flush()
            depose_le = datetime.now(UTC)
            await routeur.preparer_profil(s, compte.id, depose_le)
            depots.append((compte.id, depose_le))
        await s.commit()

    taches = [
        asyncio.create_task(routeur._analyser_en_arriere_plan(uid, "cv", None, None, t))
        for uid, t in depots
    ]
    try:
        # Laisse les N+2 tâches courir jusqu'à leur blocage respectif.
        for _ in range(100):
            await asyncio.sleep(0.02)
            if dedans >= places:
                break
        assert dedans == places, f"{dedans} analyses entrées, plafond {places}"
    finally:
        liberer.set()
        await asyncio.gather(*taches)

    assert maximum == places, f"{maximum} analyses simultanées pour un plafond de {places}"


@pytest.mark.integration
async def test_une_panne_apres_un_appel_paye_rend_la_place_ET_consigne_le_cout(
    client_auth: TestClient,
    fournisseur_courriel_espion: FournisseurCourrielEspion,
    harnais: _Harnais,
    base_profils_test: async_sessionmaker[AsyncSession],
) -> None:
    """IMPORTANT I-3, bout en bout : premier appel facturé puis illisible,
    second appel qui lève `AnalyseIndisponible`. Les deux décisions sont
    indépendantes — la place du quota revient à l'utilisateur (il n'a rien reçu)
    ET la dépense réelle apparaît dans `usage_counters`."""
    from decimal import Decimal

    from sqlalchemy import select

    from src.core.erreurs import AnalyseIndisponible
    from src.db.models import UsageCounter

    panne = AnalyseIndisponible()
    panne.cout = Decimal("0.0003")  # ce que `analyser_cv` y dépose (I-3)
    harnais.analyse.exception = panne

    _connecter(client_auth, fournisseur_courriel_espion)
    uid = await _uid(base_profils_test)
    client_auth.post("/profil/cv", files={"fichier": ("photo.jpg", JPEG)})
    corps = _attendre_fin(client_auth)

    assert (corps["etat"], corps["erreur"]) == ("echec", "analyse_indisponible")
    assert _place_du_jour(harnais.cache) == 0, "la place doit être rendue"
    async with base_profils_test() as s:
        ligne = (
            await s.execute(select(UsageCounter).where(UsageCounter.user_id == uid))
        ).scalar_one()
    assert ligne.cost_usd == Decimal("0.0003"), "la dépense réelle doit être consignée"
