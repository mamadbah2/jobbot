"""GET /offres (spec du client web §7).

Les offres ne sortent qu'à un compte connecté, et la projection est explicite :
`description` et `raw` ne doivent jamais traverser. La première pèse des
kilooctets par offre et la page a un budget de 200 Ko ; la seconde est la
charge brute du scraper.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from tests.conftest import FournisseurCourrielEspion, demander_code_verification

ADRESSE = "offres@jobbot-test.sn"


def _connecter(client: TestClient, espion: FournisseurCourrielEspion) -> None:
    code = demander_code_verification(client, espion, ADRESSE)
    r = client.post(
        "/auth/code/verifie",
        json={"email": ADRESSE, "code": code, "nom_complet": "Awa"},
    )
    assert r.status_code == 200


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

    On n'affirme pas sa position absolue : la base de développement est
    partagée, porte 232 offres réelles qu'on n'a pas le droit de purger, et
    une future passe d'ingestion pourrait y ajouter d'autres offres sans
    date. Le test serait rouge sans qu'aucun code n'ait bougé.

    Les deux offres datées de la fixture portent des dates plus récentes que
    toute offre réelle en base (max 2026-09-08), elles sont donc en tête.
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
