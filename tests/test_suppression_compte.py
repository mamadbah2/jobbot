"""DELETE /moi — « supprimer mes données » (§14.4).

Échéance fixée par le brief à la Phase 3, parce que c'est elle qui commence à
stocker des CV.
"""

from __future__ import annotations

import asyncio
import io
from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.config import get_settings
from tests.conftest import FauxCache, FournisseurCourrielEspion, demander_code_verification

ADRESSE = "suppression@jobbot-test.sn"


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
def test_supprimer_sans_cookie_refuse(client_auth: TestClient) -> None:
    assert client_auth.delete("/moi").status_code == 401


@pytest.mark.integration
def test_la_suppression_emporte_le_profil(
    client_auth: TestClient, fournisseur_courriel_espion: FournisseurCourrielEspion
) -> None:
    _connecter(client_auth, fournisseur_courriel_espion)
    client_auth.post(
        "/profil/cv",
        files={"fichier": ("cv.docx", _docx("Awa Diop comptable Alpha SARL 2019. " * 20))},
    )
    nom = get_settings().cookie_session_nom
    jeton = client_auth.cookies.get(nom)
    assert jeton
    assert client_auth.delete("/moi").status_code == 204
    # Le client a effacé son cookie : sans le reposer, le 401 ne prouverait que
    # cela. On présente donc l'ANCIEN jeton, encore valide en signature : seul le
    # compte absent peut le faire refuser.
    client_auth.cookies.set(nom, jeton)
    assert client_auth.get("/profil").status_code == 401


@pytest.mark.integration
def test_le_cookie_est_efface_a_la_suppression(
    client_auth: TestClient, fournisseur_courriel_espion: FournisseurCourrielEspion
) -> None:
    """Laisser un jeton valide pointer vers un compte supprimé enverrait
    l'utilisateur sur un 401 inexpliqué au lieu de la page de connexion."""
    _connecter(client_auth, fournisseur_courriel_espion)
    r = client_auth.delete("/moi")
    entetes = r.headers.get("set-cookie", "")
    assert get_settings().cookie_session_nom in entetes
    assert "Max-Age=0" in entetes or "expires=Thu, 01 Jan 1970" in entetes.lower()


@pytest.mark.integration
def test_se_reinscrire_apres_suppression_cree_un_compte_neuf(
    client_auth: TestClient,
    fournisseur_courriel_espion: FournisseurCourrielEspion,
    faux_cache: FauxCache,
) -> None:
    """Sinon la suppression ne serait qu'une désactivation déguisée."""
    _connecter(client_auth, fournisseur_courriel_espion)
    premier = client_auth.get("/moi").json()["id"]
    assert client_auth.delete("/moi").status_code == 204

    client_auth.cookies.clear()
    # Le délai de 60 s entre deux envois à une même adresse (`auth_cooldown_secondes`)
    # rejetterait en silence la seconde demande : le test relirait alors le code
    # déjà consommé et échouerait pour une raison étrangère à la suppression.
    # On simule son expiration plutôt que de toucher au réglage.
    cooldowns = [k for k in faux_cache.valeurs if ":cooldown:" in k]
    asyncio.run(faux_cache.expirer_maintenant(*cooldowns))
    _connecter(client_auth, fournisseur_courriel_espion)
    assert client_auth.get("/moi").json()["id"] != premier


@pytest.mark.integration
async def test_la_cascade_emporte_reellement_toutes_les_lignes(
    client_auth: TestClient,
    fournisseur_courriel_espion: FournisseurCourrielEspion,
    base_utilisateurs_test: async_sessionmaker[AsyncSession],
) -> None:
    """Vérifié en base, ligne par ligne : la promesse « le CV est effacé » est
    la plus facile à croire sans l'avoir vue. Un 401 ensuite ne prouve que la
    disparition de `users`, pas celle de `profiles` ni des compteurs."""
    from decimal import Decimal

    from sqlalchemy import func, select

    from src.api.routers import profil as routeur
    from src.db.models import Profile, UsageCounter, User

    _connecter(client_auth, fournisseur_courriel_espion)
    async with base_utilisateurs_test() as s:
        uid = (await s.execute(select(User.id).where(User.email == ADRESSE))).scalar_one()
        await routeur.preparer_profil(s, uid, datetime.now(UTC))
        await routeur.consigner_cout(
            s, uid, tokens_entree=10, tokens_sortie=5, cout_usd=Decimal("0.001")
        )
        ligne = (await s.execute(select(Profile).where(Profile.user_id == uid))).scalar_one()
        ligne.raw_cv_text = "Awa Diop, comptable chez Alpha SARL"
        ligne.structured = {"nom_complet": "Awa Diop"}
        await s.commit()

    assert client_auth.delete("/moi").status_code == 204

    async with base_utilisateurs_test() as s:
        for modele in (User, Profile, UsageCounter):
            colonne = modele.id if modele is User else modele.user_id
            compte = (
                await s.execute(select(func.count()).select_from(modele).where(colonne == uid))
            ).scalar_one()
            assert compte == 0, modele.__tablename__


@pytest.mark.integration
async def test_compte_supprime_pendant_une_analyse_ne_plante_pas_et_ne_fuit_pas(
    client_auth: TestClient,
    fournisseur_courriel_espion: FournisseurCourrielEspion,
    base_utilisateurs_test: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Constat de la revue de la tâche 6, devenu réel avec cette suppression :
    `consigner_cout` précède la vérification « profil absent », donc il heurte la
    clé étrangère de `usage_counters`. La garde extérieure doit l'absorber sans
    rien écrire ni rien laisser sortir. Le coût de l'appel déjà payé est perdu :
    c'est le comportement ÉPINGLÉ ici, pas un idéal — un compte supprimé n'a plus
    de ligne où l'imputer, et garder une trace nominative contredirait la
    suppression."""
    from contextlib import asynccontextmanager
    from decimal import Decimal

    from sqlalchemy import func, select

    from src.api.routers import profil as routeur
    from src.db.models import UsageCounter, User
    from src.llm.client import CoutAppel

    _connecter(client_auth, fournisseur_courriel_espion)
    async with base_utilisateurs_test() as s:
        uid = (await s.execute(select(User.id).where(User.email == ADRESSE))).scalar_one()
        maintenant = datetime.now(UTC)
        await routeur.preparer_profil(s, uid, maintenant)
        await s.commit()

    class _Redis:
        async def get(self, name: str) -> None:
            return None

        async def delete(self, *names: str) -> int:
            return 0

        async def aclose(self) -> None:
            return None

    async def _analyse(**kw: object) -> object:
        # Le compte disparaît PENDANT l'appel au modèle, comme en production.
        assert client_auth.delete("/moi").status_code == 204
        return {"nom_complet": "Awa"}, "transcription", CoutAppel(10, 5, 3, Decimal("0.0001"))

    @asynccontextmanager
    async def _scope() -> AsyncIterator[AsyncSession]:
        async with base_utilisateurs_test() as s:
            yield s
            await s.commit()

    monkeypatch.setattr(routeur, "analyser_cv", _analyse)
    monkeypatch.setattr(routeur, "_ouvrir_redis", lambda: _Redis())
    monkeypatch.setattr(routeur, "session_scope", _scope)

    # Ne lève pas : la dernière barrière absorbe l'erreur de clé étrangère.
    await routeur._analyser_en_arriere_plan(uid, "cv", None, None, maintenant)

    async with base_utilisateurs_test() as s:
        restants = (
            await s.execute(
                select(func.count()).select_from(UsageCounter).where(UsageCounter.user_id == uid)
            )
        ).scalar_one()
    assert restants == 0
    sortie = capsys.readouterr().out
    assert "cv_tache_de_fond_echouee" in sortie
    assert "IntegrityError" in sortie
    # Ni l'adresse ni le contenu du CV ne sortent dans le journal.
    assert ADRESSE not in sortie
    assert "transcription" not in sortie


@pytest.mark.integration
async def test_la_suppression_emporte_l_image_du_cv_en_attente(
    client_auth: TestClient,
    fournisseur_courriel_espion: FournisseurCourrielEspion,
    faux_cache: FauxCache,
    base_utilisateurs_test: async_sessionmaker[AsyncSession],
) -> None:
    """L'image brute d'un CV est la donnée la plus sensible du produit : si le
    process meurt avant que la tâche de fond la consomme, elle survivrait dix
    minutes à une suppression annoncée immédiate."""
    from sqlalchemy import select

    from src.api.routers.profil import cle_image_cv
    from src.db.models import User

    _connecter(client_auth, fournisseur_courriel_espion)
    async with base_utilisateurs_test() as s:
        uid = (await s.execute(select(User.id).where(User.email == ADRESSE))).scalar_one()
    cle = cle_image_cv(uid)
    await faux_cache.set(cle, b"\xff\xd8\xff octets bruts", ex=600)

    assert client_auth.delete("/moi").status_code == 204

    assert await faux_cache.get(cle) is None
