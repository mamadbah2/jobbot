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


async def test_refuse_une_url_interdite_par_le_robots_txt_charge() -> None:
    """Les règles lues à l'exécution priment sur la liste noire en dur."""
    from src.ingest.robots import ReglesRobots

    horloge = HorlogeFactice()
    poli = _client(horloge, regles=ReglesRobots.analyser("User-agent: *\nDisallow: /prive/\n", UA))
    with pytest.raises(CheminInterditError):
        await poli.get("https://exemple.sn/prive/x")


async def test_autorise_toujours_la_lecture_de_robots_txt() -> None:
    """Sans exception, on ne pourrait jamais relire le fichier lui-même."""
    from src.ingest.robots import ReglesRobots

    horloge = HorlogeFactice()
    poli = _client(horloge, regles=ReglesRobots.analyser("User-agent: *\nDisallow: /\n", UA))
    assert (await poli.get("https://exemple.sn/robots.txt")).status_code == 200


async def test_la_liste_noire_en_dur_reste_un_plancher() -> None:
    """Si robots.txt est injoignable, les chemins sensibles restent refusés."""
    horloge = HorlogeFactice()
    poli = _client(horloge, chemins_interdits=("/resume/",), regles=None)
    with pytest.raises(CheminInterditError):
        await poli.get("https://exemple.sn/resume/x")


# --- Garde-fous de §2.4 contre une URL fournie par le site lui-même ---


async def test_refuse_un_client_qui_suit_les_redirections() -> None:
    """Une redirection échappe à TOUS les contrôles : chemin, robots et délai.

    Le contrôle a lieu avant l'appel ; les sauts suivants ne repassent jamais
    devant. Le refus est donc structurel, à la construction.
    """
    with pytest.raises(ValueError, match="redirection"):
        PoliteClient(
            httpx.AsyncClient(follow_redirects=True),
            user_agent=UA,
            delai=0.0,
            horloge=HorlogeFactice().monotonic,
            dormir=HorlogeFactice().dormir,
        )


async def test_refuse_une_url_hors_des_hotes_autorises() -> None:
    """Les URL d'annonces viennent d'un href du site : on ne les suit pas à l'aveugle."""
    horloge = HorlogeFactice()
    poli = _client(horloge, hotes_autorises=frozenset({"exemple.sn"}))
    with pytest.raises(CheminInterditError):
        await poli.get("https://collecteur-externe.example/exfiltration?d=1")


async def test_autorise_le_sous_domaine_www_du_meme_hote() -> None:
    horloge = HorlogeFactice()
    poli = _client(horloge, hotes_autorises=frozenset({"exemple.sn"}))
    assert (await poli.get("https://www.exemple.sn/offre-demploi/x/")).status_code == 200


async def test_refuse_un_chemin_interdit_atteint_par_traversee() -> None:
    """`..` est résolu par httpx APRÈS notre contrôle : il faut contrôler le chemin final."""
    horloge = HorlogeFactice()
    poli = _client(horloge, chemins_interdits=("/resume/",))
    with pytest.raises(CheminInterditError):
        await poli.get("https://exemple.sn/offre-demploi/x/../../resume/candidat-42")


async def test_refuse_un_chemin_interdit_ecrit_avec_un_double_slash() -> None:
    horloge = HorlogeFactice()
    poli = _client(horloge, chemins_interdits=("/resume/",))
    with pytest.raises(CheminInterditError):
        await poli.get("https://exemple.sn//resume/candidat-42")


async def test_refuse_un_chemin_interdit_encode_en_pourcent() -> None:
    horloge = HorlogeFactice()
    poli = _client(horloge, chemins_interdits=("/resume/",))
    with pytest.raises(CheminInterditError):
        await poli.get("https://exemple.sn/resum%65/candidat-42")
