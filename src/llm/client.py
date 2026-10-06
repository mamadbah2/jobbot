"""Client DeepSeek unique. Aucun appel au LLM ailleurs dans le dépôt (§9).

Tarifs et noms de modèles **relevés le 2026-10-06** contre l'API officielle, pas
recopiés du brief : le §9 nommait `deepseek-chat`, qui n'existe plus. Ces valeurs
sont datées et se revérifient.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from openai import APIConnectionError, APIStatusError, APITimeoutError, AsyncOpenAI

from src.core.erreurs import AnalyseIndisponible
from src.logging_setup import get_logger

log = get_logger(__name__)

# Dollars par million de tokens, hors pointe. La pointe double ces valeurs.
_TARIFS: dict[str, tuple[Decimal, Decimal, Decimal]] = {
    # modèle: (entrée servie par le cache, entrée fraîche, sortie)
    "deepseek-flash": (Decimal("0.003"), Decimal("0.15"), Decimal("0.6")),
    "deepseek-v4-pro": (Decimal("0.022"), Decimal("0.66"), Decimal("1.98")),
}

# Seuls modèles qui lisent les images : `deepseek-v4-pro` est texte seul, et
# DEEPSEEK_MODELE est configurable. Sans ce garde-fou, changer une variable
# d'environnement casserait l'analyse des photos de CV en 400 payant.
_MODELES_IMAGE = frozenset({"deepseek-flash"})

_MILLION = Decimal(1_000_000)
# 01:00-04:00 et 06:00-10:00 UTC, du lundi au vendredi.
_HEURES_DE_POINTE = frozenset({1, 2, 3, 6, 7, 8, 9})


def modele_lit_les_images(modele: str) -> bool:
    return modele in _MODELES_IMAGE


def est_en_pointe(moment: datetime) -> bool:
    """Le week-end n'est jamais en pointe : ne regarder que l'heure
    surfacturerait tous les samedis et dimanches du double.

    La grille officielle exclut aussi les jours fériés chinois (relevé le
    2026-10-06). On ne les connaît pas, donc on les facture au tarif de pointe :
    l'erreur va dans le bon sens — on surestime la dépense, jamais l'inverse —
    et tenir un calendrier férié chinois à jour pour quelques jours par an serait
    de la sur-ingénierie (§2.5).
    """
    return moment.weekday() < 5 and moment.hour in _HEURES_DE_POINTE


@dataclass(frozen=True, slots=True)
class CoutAppel:
    tokens_entree_cache: int
    tokens_entree_frais: int
    tokens_sortie: int
    cout_usd: Decimal


def calculer_cout(
    modele: str,
    tokens_entree_cache: int,
    tokens_entree_frais: int,
    tokens_sortie: int,
    *,
    moment: datetime | None = None,
) -> Decimal:
    """Coût en dollars d'un appel.

    `moment` est injectable pour que le test puisse se placer en pointe ou en
    heure creuse sans attendre la bonne heure.
    """
    if modele not in _TARIFS:
        # Facturer 0 un modèle inconnu ferait croire que le produit ne coûte
        # rien : l'erreur qu'on ne verrait jamais dans un tableau de bord.
        raise ValueError(f"tarif inconnu pour le modèle {modele!r}")

    tarif_cache, tarif_frais, tarif_sortie = _TARIFS[modele]
    facteur = Decimal(2) if est_en_pointe(moment or datetime.now(UTC)) else Decimal(1)
    return (
        (
            Decimal(tokens_entree_cache) * tarif_cache
            + Decimal(tokens_entree_frais) * tarif_frais
            + Decimal(tokens_sortie) * tarif_sortie
        )
        / _MILLION
        * facteur
    )


_TENTATIVES = 3
_ATTENTE_INITIALE_S = 1.0
_DELAI_MAX_S = 60.0
_URL_DEEPSEEK = "https://api.deepseek.com"


def _creer_client(cle_api: str) -> AsyncOpenAI:
    return AsyncOpenAI(api_key=cle_api, base_url=_URL_DEEPSEEK, timeout=_DELAI_MAX_S)


def _contient_image(messages: list[dict[str, Any]]) -> bool:
    for message in messages:
        contenu = message.get("content")
        if isinstance(contenu, list) and any(
            isinstance(p, dict) and p.get("type") == "image_url" for p in contenu
        ):
            return True
    return False


def _compteurs(usage: Any) -> tuple[int, int, int]:
    """(entrée servie par le cache, entrée fraîche, sortie).

    `prompt_cache_miss_tokens == 0` est une VRAIE valeur (le cache a servi tout
    le prompt) : elle ne doit pas être confondue avec « champ absent ». Seule
    l'absence déclenche le repli, et celui-ci soustrait le cache de
    `prompt_tokens` (qui l'inclut) au lieu de le recompter au tarif frais.
    """
    if usage is None:
        log.warning("deepseek_usage_absent")
        return 0, 0, 0
    cache_touche = getattr(usage, "prompt_cache_hit_tokens", None) or 0
    manque = getattr(usage, "prompt_cache_miss_tokens", None)
    frais = manque if manque is not None else max(usage.prompt_tokens - cache_touche, 0)
    return cache_touche, frais, usage.completion_tokens


async def appeler_deepseek(
    messages: list[dict[str, Any]],
    *,
    modele: str,
    cle_api: str,
    temperature: float,
    client: Any | None = None,
    dormir: Callable[[float], Awaitable[None]] = asyncio.sleep,
    moment: datetime | None = None,
) -> tuple[str, CoutAppel]:
    """Un appel, avec relance exponentielle sur 429 et 5xx (§9).

    Rend le texte de la réponse et le coût. Lève `AnalyseIndisponible` quand
    DeepSeek reste injoignable : l'appelant doit alors NE PAS décompter le quota.

    `client`, `dormir` et `moment` sont injectables, sur le même patron que
    `analyser_cv` qui injecte `appeler` : aucun test ne sort sur le réseau.

    Aucun fragment de message n'est journalisé : les messages portent le CV.
    Les erreurs sont levées HORS des blocs `except` : levées dedans, même avec
    `from None`, `__context__` garderait l'exception d'origine et son message.
    """
    if _contient_image(messages) and not modele_lit_les_images(modele):
        raise ValueError(f"le modèle {modele!r} ne lit pas les images")

    sdk: Any = client if client is not None else _creer_client(cle_api)
    attente = _ATTENTE_INITIALE_S
    for tentative in range(1, _TENTATIVES + 1):
        refusee = False
        try:
            reponse = await sdk.chat.completions.create(
                model=modele, messages=messages, temperature=temperature
            )
        except (APITimeoutError, APIConnectionError) as exc:
            motif = type(exc).__name__
        except APIStatusError as exc:
            motif = f"http_{exc.status_code}"
            # 4xx autre que 429 : la requête est fautive, relancer à
            # l'identique ne changerait rien et coûterait du temps.
            refusee = exc.status_code != 429 and exc.status_code < 500
        else:
            cache_touche, frais, sortie = _compteurs(reponse.usage)
            return (reponse.choices[0].message.content or ""), CoutAppel(
                tokens_entree_cache=cache_touche,
                tokens_entree_frais=frais,
                tokens_sortie=sortie,
                cout_usd=calculer_cout(modele, cache_touche, frais, sortie, moment=moment),
            )

        if refusee:
            log.error("deepseek_requete_refusee", motif=motif)
            raise AnalyseIndisponible
        log.warning("deepseek_relance", tentative=tentative, motif=motif)
        if tentative < _TENTATIVES:
            await dormir(attente)
            attente *= 2

    log.error("deepseek_injoignable", tentatives=_TENTATIVES)
    raise AnalyseIndisponible
