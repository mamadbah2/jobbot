"""POST /profil/cv, GET /profil, PUT /profil (spec §7)."""

from __future__ import annotations

import io
from collections.abc import AsyncIterator

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
def test_un_depot_valide_passe_en_cours_et_rend_202(
    client_auth: TestClient, fournisseur_courriel_espion: FournisseurCourrielEspion
) -> None:
    """La réponse ne doit JAMAIS attendre l'analyse : l'utilisateur est sur 3G."""
    _connecter(client_auth, fournisseur_courriel_espion)
    contenu = _docx("Awa Diop comptable chez Alpha SARL depuis 2019. " * 20)
    r = client_auth.post("/profil/cv", files={"fichier": ("cv.docx", contenu)})
    assert r.status_code == 202
    assert r.json()["etat"] == "en_cours"


@pytest.mark.integration
def test_deux_depots_simultanes_ne_laissent_quun_seul_etat(
    client_auth: TestClient, fournisseur_courriel_espion: FournisseurCourrielEspion
) -> None:
    """Review Focus n°5 : deux tâches de fond écrivant la même ligne `profiles`.
    La contrainte d'unicité sur `profiles.user_id` interdit déjà deux lignes ;
    ce test vérifie qu'un second dépôt ne casse pas et laisse un état cohérent."""
    _connecter(client_auth, fournisseur_courriel_espion)
    contenu = _docx("Awa Diop comptable chez Alpha SARL depuis 2019. " * 20)
    r1 = client_auth.post("/profil/cv", files={"fichier": ("cv.docx", contenu)})
    r2 = client_auth.post("/profil/cv", files={"fichier": ("cv.docx", contenu)})
    assert r1.status_code == 202
    assert r2.status_code == 202
    assert client_auth.get("/profil").json()["etat"] in ("en_cours", "pret", "echec")


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
