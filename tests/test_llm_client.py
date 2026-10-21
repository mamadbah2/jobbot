"""Calcul du coût d'un appel DeepSeek, et robustesse du client.

Tarifs relevés le 2026-10-06 sur l'API officielle. Ils sont DATÉS : si le test
échoue un jour parce que DeepSeek a changé sa grille, c'est le test qui dit la
vérité sur ce qu'on croyait, pas la grille qui a tort.

Aucune sortie réseau : client et attente sont injectés.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from openai import APIStatusError, APITimeoutError

from src.core.erreurs import AnalyseIndisponible
from src.llm.client import _creer_client, appeler_deepseek, calculer_cout

HORS_POINTE = datetime(2026, 10, 1, 14, 0, tzinfo=UTC)  # jeudi 14h UTC
EN_POINTE = datetime(2026, 10, 1, 7, 0, tzinfo=UTC)  # jeudi 7h UTC
WEEKEND_MEME_HEURE = datetime(2026, 10, 3, 7, 0, tzinfo=UTC)  # samedi 7h UTC


def test_le_cache_coute_cinquante_fois_moins_que_lentree_fraiche() -> None:
    """Confondre les deux fausse le suivi de coût massivement."""
    cache = calculer_cout("deepseek-flash", 1_000_000, 0, 0, moment=HORS_POINTE)
    frais = calculer_cout("deepseek-flash", 0, 1_000_000, 0, moment=HORS_POINTE)
    assert cache == Decimal("0.003")
    assert frais == Decimal("0.15")


def test_le_tarif_de_pointe_double_tout() -> None:
    creux = calculer_cout("deepseek-flash", 0, 1_000_000, 1_000_000, moment=HORS_POINTE)
    pointe = calculer_cout("deepseek-flash", 0, 1_000_000, 1_000_000, moment=EN_POINTE)
    assert pointe == creux * 2


def test_le_week_end_nest_jamais_en_pointe() -> None:
    """Les heures de pointe sont du lundi au vendredi : un calcul qui ne
    regarde que l'heure surfacture tout le week-end."""
    assert calculer_cout(
        "deepseek-flash", 0, 1_000_000, 0, moment=WEEKEND_MEME_HEURE
    ) == Decimal("0.15")


def test_la_grille_complete_au_centime() -> None:
    """Toute la grille relevée le 2026-10-06, sortie comprise, pour les deux modèles."""
    assert calculer_cout(
        "deepseek-flash", 0, 0, 1_000_000, moment=HORS_POINTE
    ) == Decimal("0.6")
    assert calculer_cout(
        "deepseek-v4-pro", 1_000_000, 0, 0, moment=HORS_POINTE
    ) == Decimal("0.022")
    assert calculer_cout(
        "deepseek-v4-pro", 0, 1_000_000, 0, moment=HORS_POINTE
    ) == Decimal("0.66")
    assert calculer_cout(
        "deepseek-v4-pro", 0, 0, 1_000_000, moment=HORS_POINTE
    ) == Decimal("1.98")


def test_les_bornes_des_heures_de_pointe() -> None:
    """01:00-04:00 et 06:00-10:00 : 04:00 et 10:00 sont déjà hors pointe,
    00:xx et 05:xx aussi."""
    cas = [(0, 1), (1, 2), (3, 2), (4, 1), (5, 1), (6, 2), (9, 2), (10, 1)]
    for heure, facteur in cas:
        moment = datetime(2026, 10, 1, heure, 0, tzinfo=UTC)
        cout = calculer_cout("deepseek-flash", 0, 1_000_000, 0, moment=moment)
        assert cout == Decimal("0.15") * facteur, heure


def test_le_modele_pro_est_plus_cher_que_flash() -> None:
    flash = calculer_cout("deepseek-flash", 0, 1_000_000, 0, moment=HORS_POINTE)
    pro = calculer_cout("deepseek-v4-pro", 0, 1_000_000, 0, moment=HORS_POINTE)
    assert pro > flash


def test_un_modele_inconnu_est_refuse_plutot_que_facture_a_zero() -> None:
    """Un tarif inconnu facturé 0 ferait croire que le produit ne coûte rien —
    exactement l'erreur qu'on ne verrait jamais dans un tableau de bord."""
    with pytest.raises(ValueError):
        calculer_cout("modele-invente", 0, 1000, 0, moment=HORS_POINTE)


def test_un_cv_coute_moins_que_le_plafond_du_brief() -> None:
    """Le §9 fixe 15 FCFA par candidature. Ordre de grandeur d'un CV :
    2 000 tokens en entrée, 1 500 en sortie."""
    cout_usd = calculer_cout("deepseek-flash", 0, 2000, 1500, moment=EN_POINTE)
    assert cout_usd * 600 < Decimal("15")  # ~600 FCFA pour 1 USD


# --- appeler_deepseek : client et attente injectés ---

_REQUETE = httpx.Request("POST", "https://api.deepseek.com/chat/completions")


def _statut(code: int) -> APIStatusError:
    reponse = httpx.Response(code, request=_REQUETE)
    return APIStatusError("erreur", response=reponse, body=None)


def _reponse(hit: int | None, miss: int | None, total: int, sortie: int) -> Any:
    usage = SimpleNamespace(prompt_tokens=total, completion_tokens=sortie)
    if hit is not None:
        usage.prompt_cache_hit_tokens = hit
    if miss is not None:
        usage.prompt_cache_miss_tokens = miss
    message = SimpleNamespace(content="{}")
    return SimpleNamespace(usage=usage, choices=[SimpleNamespace(message=message)])


class FauxClient:
    """Rejoue un scénario : chaque élément est une exception levée ou une réponse rendue."""

    def __init__(self, scenario: list[Any]) -> None:
        self._scenario = list(scenario)
        self.appels: list[dict[str, Any]] = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    async def _create(self, **kwargs: Any) -> Any:
        self.appels.append(kwargs)
        suite = self._scenario.pop(0)
        if isinstance(suite, Exception):
            raise suite
        return suite


class Horloge:
    def __init__(self) -> None:
        self.attentes: list[float] = []

    async def dormir(self, secondes: float) -> None:
        self.attentes.append(secondes)


async def _appel(client: FauxClient, horloge: Horloge) -> tuple[str, Any]:
    return await appeler_deepseek(
        [{"role": "user", "content": "x"}],
        modele="deepseek-flash",
        cle_api="cle",
        temperature=0.3,
        client=client,
        dormir=horloge.dormir,
        moment=HORS_POINTE,
    )


async def test_un_prompt_entierement_servi_par_le_cache_est_facture_au_tarif_cache() -> None:
    """`miss == 0` est une vraie valeur, pas un champ absent : la confondre
    avec l'absence facturerait 2 000 tokens cachés au tarif frais (x50)."""
    client = FauxClient([_reponse(hit=2000, miss=0, total=2000, sortie=0)])
    _, cout = await _appel(client, Horloge())
    assert cout.tokens_entree_cache == 2000
    assert cout.tokens_entree_frais == 0
    assert cout.cout_usd == Decimal("0.000006")


async def test_sans_champs_de_cache_lentree_est_comptee_une_fois() -> None:
    """Repli quand DeepSeek n'envoie pas les champs : jamais zéro entrée."""
    client = FauxClient([_reponse(hit=None, miss=None, total=1000, sortie=0)])
    _, cout = await _appel(client, Horloge())
    assert (cout.tokens_entree_cache, cout.tokens_entree_frais) == (0, 1000)


async def test_la_temperature_et_le_modele_atteignent_le_sdk() -> None:
    client = FauxClient([_reponse(0, 10, 10, 5)])
    await _appel(client, Horloge())
    assert client.appels[0]["temperature"] == 0.3
    assert client.appels[0]["model"] == "deepseek-flash"


async def test_un_429_est_relance_avec_attente() -> None:
    client, horloge = FauxClient([_statut(429), _reponse(0, 10, 10, 5)]), Horloge()
    await _appel(client, horloge)
    assert len(client.appels) == 2
    assert horloge.attentes == [1.0]


async def test_un_4xx_fautif_nest_pas_relance() -> None:
    client, horloge = FauxClient([_statut(400)]), Horloge()
    with pytest.raises(AnalyseIndisponible):
        await _appel(client, horloge)
    assert len(client.appels) == 1
    assert horloge.attentes == []


async def test_trois_echecs_abandonnent_avec_attente_exponentielle() -> None:
    client = FauxClient([_statut(503), APITimeoutError(request=_REQUETE), _statut(500)])
    horloge = Horloge()
    with pytest.raises(AnalyseIndisponible) as info:
        await _appel(client, horloge)
    assert len(client.appels) == 3
    assert horloge.attentes == [1.0, 2.0]  # pas d'attente après la dernière
    assert info.value.__context__ is None


async def test_un_modele_texte_seul_ne_recoit_pas_dimage() -> None:
    client = FauxClient([])
    messages: list[dict[str, Any]] = [
        {"role": "user", "content": [{"type": "image_url", "image_url": {"url": "x"}}]}
    ]
    with pytest.raises(ValueError):
        await appeler_deepseek(
            messages, modele="deepseek-v4-pro", cle_api="cle", temperature=0.3, client=client
        )
    assert client.appels == []


def test_le_client_reel_a_le_delai_et_ladresse_du_brief() -> None:
    client = _creer_client("cle")
    assert client.timeout == 60.0
    assert str(client.base_url).startswith("https://api.deepseek.com")
