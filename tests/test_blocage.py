"""Détection d'un blocage anti-bot (CLAUDE.md §2 interdiction n°4, §7).

Si le site passe sous challenge Cloudflare, insister est le pire choix :
on ne sait pas le franchir (et on n'a pas le droit d'essayer), et l'acharnement
mène au bannissement de l'IP du VPS, ce qui tuerait TOUS les scrapers.
La seule conduite correcte : arrêter la source et alerter.
"""

from __future__ import annotations

import time

import httpx
import pytest

from src.ingest.base import PoliteClient, SourceBloqueeError

CHALLENGE = (
    '<!DOCTYPE html><html><head><title>Just a moment...</title>'
    '<meta http-equiv="refresh" content="0"></head><body>'
    '<div id="cf-challenge-running"></div></body></html>'
)


def _client(reponse: httpx.Response) -> PoliteClient:
    async def dormir(_: float) -> None:
        return None

    return PoliteClient(
        httpx.AsyncClient(transport=httpx.MockTransport(lambda _r: reponse)),
        user_agent="JobBotSN/0.1",
        delai=0.0,
        horloge=time.monotonic,
        dormir=dormir,
    )


async def test_leve_sur_un_challenge_cloudflare() -> None:
    with pytest.raises(SourceBloqueeError):
        await _client(httpx.Response(403, text=CHALLENGE)).get("https://exemple.sn/a")


async def test_leve_aussi_quand_le_challenge_arrive_en_503() -> None:
    with pytest.raises(SourceBloqueeError):
        await _client(httpx.Response(503, text=CHALLENGE)).get("https://exemple.sn/a")


async def test_leve_sur_l_entete_cf_mitigated() -> None:
    """Cloudflare signale parfois le challenge par un en-tête plutôt qu'un corps."""
    reponse = httpx.Response(403, headers={"cf-mitigated": "challenge"}, text="")
    with pytest.raises(SourceBloqueeError):
        await _client(reponse).get("https://exemple.sn/a")


async def test_un_403_ordinaire_n_est_pas_un_blocage_anti_bot() -> None:
    """Une page simplement interdite n'est pas un signal d'arrêt de la source."""
    reponse = await _client(httpx.Response(403, text="<h1>Forbidden</h1>")).get(
        "https://exemple.sn/a"
    )
    assert reponse.status_code == 403


async def test_une_reponse_normale_passe() -> None:
    reponse = await _client(httpx.Response(200, text="<html>ok</html>")).get(
        "https://exemple.sn/a"
    )
    assert reponse.status_code == 200


async def test_le_message_d_erreur_nomme_la_source_pour_l_alerte_admin() -> None:
    """L'admin doit savoir QUEL site s'est fermé, sans lire les logs bruts (§7)."""
    with pytest.raises(SourceBloqueeError, match="exemple.sn"):
        await _client(httpx.Response(403, text=CHALLENGE)).get("https://exemple.sn/a")
