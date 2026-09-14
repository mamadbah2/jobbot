"""GET /offres (spec du client web §7).

Les offres ne sortent qu'à un compte connecté, et la projection est explicite :
`description` et `raw` ne doivent jamais traverser. La première pèse des
kilooctets par offre et la page a un budget de 200 Ko ; la seconde est la
charge brute du scraper.
"""

from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from src.api.routers import offres as offres_router
from tests.conftest import FournisseurCourrielEspion, demander_code_verification

ADRESSE = "offres@jobbot-test.sn"


def _connecter(client: TestClient, espion: FournisseurCourrielEspion) -> None:
    code = demander_code_verification(client, espion, ADRESSE)
    r = client.post(
        "/auth/code/verifie",
        json={"email": ADRESSE, "code": code, "nom_complet": "Awa"},
    )
    assert r.status_code == 200


@pytest.fixture(autouse=True)
def neutraliser_rafraichissement(monkeypatch: pytest.MonkeyPatch) -> None:
    """Neutralise par défaut le rafraîchissement de fond déclenché par `GET /offres`.

    `_rafraichir_en_arriere_plan` construit délibérément son propre client
    Redis (piège n°1 du brief de la tâche 2) : il échappe donc à
    `app.dependency_overrides[deps.cache_redis]` que `client_auth` installe
    pour le reste de l'API. Dans ce worktree, `redis://redis:6379/0` (URL par
    défaut) ne résout pas depuis l'hôte, donc c'est inoffensif — mais lancés
    depuis le réseau Docker (le mode normal du projet), ces tests prendraient
    le verrou et déclencheraient une vraie passe de scraping contre
    emploidakar.com, qui écrirait dans la base de développement partagée aux
    232 offres réelles. Contraire à §2.4 et à l'interdiction de tout
    scraping déclenché par un test. Le test dédié plus bas réinstalle son
    propre espion pour prouver que la planification a bien lieu.
    """

    async def _noop() -> None:
        return None

    monkeypatch.setattr(offres_router, "_rafraichir_en_arriere_plan", _noop)


@pytest.mark.integration
def test_offres_planifie_le_rafraichissement(
    client_auth: TestClient,
    fournisseur_courriel_espion: FournisseurCourrielEspion,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Aucun autre test ne le prouve : ils neutralisent tous la tâche de fond
    (fixture `neutraliser_rafraichissement` ci-dessus). Un espion — jamais un
    vrai client Redis, cf. §2.4 — pour vérifier que `GET /offres` planifie
    réellement `_rafraichir_en_arriere_plan`, sans attendre sa fin dans la
    réponse HTTP (elle doit rester rapide, spec §7)."""
    appels = 0

    async def _espion() -> None:
        nonlocal appels
        appels += 1

    monkeypatch.setattr(offres_router, "_rafraichir_en_arriere_plan", _espion)

    _connecter(client_auth, fournisseur_courriel_espion)
    assert client_auth.get("/offres").status_code == 200

    # La tâche est planifiée par `asyncio.create_task` et rend la main tout
    # de suite (spec §7) : elle peut donc s'exécuter juste après la réponse.
    # `TestClient` tourne sur une boucle d'évènements persistante ; une courte
    # attente active borne l'incertitude de timing sans sommeil arbitraire.
    for _ in range(50):
        if appels:
            break
        time.sleep(0.01)
    assert appels >= 1, "GET /offres doit planifier une tâche de fond"


@pytest.mark.integration
def test_feuilleter_ne_redeclenche_pas_le_rafraichissement(
    client_auth: TestClient,
    fournisseur_courriel_espion: FournisseurCourrielEspion,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Seule la première page déclenche une passe.

    Sans cette garde, chaque page feuilletée ouvrait un client Redis neuf
    pour une décision toujours négative : le repère de fraîcheur venait
    d'être posé par la page 1. Le coût est invisible, donc il ne se
    remarquerait jamais sans un test qui le nomme.
    """
    appels = 0

    async def _espion() -> None:
        nonlocal appels
        appels += 1

    monkeypatch.setattr(offres_router, "_rafraichir_en_arriere_plan", _espion)

    _connecter(client_auth, fournisseur_courriel_espion)
    assert client_auth.get("/offres", params={"decalage": 20}).status_code == 200

    # Même attente active que le test ci-dessus : si une tâche était planifiée,
    # elle aurait tout le temps de s'exécuter dans cet intervalle.
    for _ in range(50):
        if appels:
            break
        time.sleep(0.01)
    assert appels == 0, "une page au-delà de la première ne doit rien déclencher"


@pytest.mark.integration
def test_offres_sans_cookie_refuse(client_auth: TestClient) -> None:
    r = client_auth.get("/offres")
    assert r.status_code == 401
    assert r.json()["erreur"] == "jeton_invalide"


@pytest.mark.integration
def test_offres_listees_pour_un_compte_connecte(
    client_auth: TestClient,
    fournisseur_courriel_espion: FournisseurCourrielEspion,
    offres_test: list[int],
) -> None:
    _connecter(client_auth, fournisseur_courriel_espion)
    r = client_auth.get("/offres", params={"limite": 50})
    assert r.status_code == 200
    corps = r.json()
    titres = [o["titre"] for o in corps["offres"]]
    assert "Comptable" in titres
    assert corps["total"] >= 3


@pytest.mark.integration
def test_la_description_et_la_charge_brute_ne_sortent_jamais(
    client_auth: TestClient,
    fournisseur_courriel_espion: FournisseurCourrielEspion,
    offres_test: list[int],
) -> None:
    """Le test qui compte pour le budget de 200 Ko."""
    _connecter(client_auth, fournisseur_courriel_espion)
    r = client_auth.get("/offres", params={"limite": 50})
    for offre in r.json()["offres"]:
        assert "description" not in offre
        assert "raw" not in offre
        assert "fingerprint" not in offre
        assert "source_id" not in offre


@pytest.mark.integration
def test_les_offres_sans_date_ne_passent_pas_en_tete(
    client_auth: TestClient,
    fournisseur_courriel_espion: FournisseurCourrielEspion,
    offres_test: list[int],
) -> None:
    """Sans `NULLS LAST`, Postgres remonte les NULL en TÊTE sur un DESC :
    « Sans date » serait alors la première ligne de la première page.

    On n'affirme pas la position absolue des offres de la fixture : la base
    de développement est partagée et porte des centaines d'offres réelles
    qu'on n'a pas le droit de purger. On affirme leur ORDRE RELATIF, que
    leurs dates en 2099 rendent indépendant des données réelles : aucune
    offre ingérée ne peut passer devant elles.

    La seconde assertion, elle, est robuste par construction et sans aucune
    hypothèse sur les données : sans `NULLS LAST`, « Sans date » serait en
    position 1 quel que soit le contenu de la base.
    """
    _connecter(client_auth, fournisseur_courriel_espion)
    premiere_page = client_auth.get("/offres", params={"limite": 50}).json()["offres"]
    titres = [o["titre"] for o in premiere_page if o["id"] in offres_test]

    assert titres == ["Developpeur", "Comptable"], (
        "les deux offres datées doivent être en tête, de la plus récente à la plus ancienne"
    )
    assert "Sans date" not in [o["titre"] for o in premiere_page], (
        "une offre sans date remontée en première page = NULLS LAST a disparu du tri"
    )


@pytest.mark.integration
def test_pagination(
    client_auth: TestClient,
    fournisseur_courriel_espion: FournisseurCourrielEspion,
    offres_test: list[int],
) -> None:
    _connecter(client_auth, fournisseur_courriel_espion)
    page1 = client_auth.get("/offres", params={"limite": 2, "decalage": 0}).json()
    page2 = client_auth.get("/offres", params={"limite": 2, "decalage": 2}).json()
    assert len(page1["offres"]) == 2
    ids1 = {o["id"] for o in page1["offres"]}
    ids2 = {o["id"] for o in page2["offres"]}
    assert not (ids1 & ids2), "deux pages successives ne doivent pas se recouvrir"


@pytest.mark.integration
def test_la_limite_est_plafonnee(
    client_auth: TestClient, fournisseur_courriel_espion: FournisseurCourrielEspion
) -> None:
    _connecter(client_auth, fournisseur_courriel_espion)
    assert client_auth.get("/offres", params={"limite": 500}).status_code == 422
