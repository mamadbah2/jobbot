"""Politesse HTTP des scrapers (CLAUDE.md §2, interdiction n°4).

« Ne jamais scraper sans délai ni User-Agent identifiable. Respect de
robots.txt, 1 requête / 3-5 s par domaine. » Ces tests verrouillent la règle :
sans eux, un refactor peut supprimer le délai sans que rien ne le signale.
"""

from __future__ import annotations

import httpx
import pytest

from src.ingest.base import CheminInterditError, PoliteClient

UA = "JobBotSN/0.1 (+contact: admin@example.sn)"


class HorlogeFactice:
    """Horloge et sommeil simulés : les tests ne doivent pas attendre vraiment."""

    def __init__(self) -> None:
        self.maintenant = 0.0
        self.sommeils: list[float] = []

    def monotonic(self) -> float:
        return self.maintenant

    async def dormir(self, duree: float) -> None:
        self.sommeils.append(duree)
        self.maintenant += duree


def _client(horloge: HorlogeFactice, **kwargs: object) -> PoliteClient:
    requetes: list[httpx.Request] = []

    def repondre(request: httpx.Request) -> httpx.Response:
        requetes.append(request)
        return httpx.Response(200, text="ok")

    transport = httpx.MockTransport(repondre)
    poli = PoliteClient(
        httpx.AsyncClient(transport=transport),
        user_agent=UA,
        delai=4.0,
        horloge=horloge.monotonic,
        dormir=horloge.dormir,
        **kwargs,  # type: ignore[arg-type]
    )
    poli.requetes_vues = requetes  # type: ignore[attr-defined]
    return poli


async def test_envoie_le_user_agent_identifiable() -> None:
    horloge = HorlogeFactice()
    poli = _client(horloge)
    await poli.get("https://exemple.sn/a")
    assert poli.requetes_vues[0].headers["user-agent"] == UA  # type: ignore[attr-defined]


async def test_espace_deux_requetes_du_meme_domaine() -> None:
    horloge = HorlogeFactice()
    poli = _client(horloge)
    await poli.get("https://exemple.sn/a")
    await poli.get("https://exemple.sn/b")
    assert horloge.sommeils and horloge.sommeils[0] >= 4.0


async def test_n_attend_pas_avant_la_toute_premiere_requete() -> None:
    horloge = HorlogeFactice()
    poli = _client(horloge)
    await poli.get("https://exemple.sn/a")
    assert horloge.sommeils == []


async def test_le_delai_est_compte_par_domaine() -> None:
    """Deux domaines distincts ne se ralentissent pas mutuellement."""
    horloge = HorlogeFactice()
    poli = _client(horloge)
    await poli.get("https://exemple.sn/a")
    await poli.get("https://autre.sn/a")
    assert horloge.sommeils == []


async def test_refuse_un_chemin_interdit_par_robots_txt() -> None:
    """§7 : /resume/ et /CV/ d'emploidakar sont des CV de tiers, interdits."""
    horloge = HorlogeFactice()
    poli = _client(horloge, chemins_interdits=("/resume/", "/cv/"))
    with pytest.raises(CheminInterditError):
        await poli.get("https://exemple.sn/resume/quelquun")


async def test_autorise_un_chemin_normal_malgre_la_liste_noire() -> None:
    horloge = HorlogeFactice()
    poli = _client(horloge, chemins_interdits=("/resume/", "/cv/"))
    reponse = await poli.get("https://exemple.sn/offre-demploi/chef-de-parc/")
    assert reponse.status_code == 200
