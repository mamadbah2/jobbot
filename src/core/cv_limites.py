"""Plafond d'analyses de CV par utilisateur et par jour.

C'est d'abord un plafond de COÛT : chaque analyse est un appel payé à DeepSeek,
et une boucle de redépôt viderait la marge de l'abonnement (§9). C'est ensuite un
garde-fou anti-abus.

Indexé sur l'utilisateur et non sur l'IP : contrairement à l'inscription, on sait
qui demande — il est authentifié. Le piège de la Phase 2, où tous les
utilisateurs tombaient dans le même seau derrière un proxy, n'a donc pas d'objet
ici.
"""

from __future__ import annotations

from src.core.cache import CacheRedis
from src.core.erreurs import TropDAnalyses
from src.core.limites import empreinte, fenetre_jour, incrementer

_PREFIXE = "jobbot:cv:analyses"
_UN_JOUR = 86_400


def _cle(user_id: int, secret: str) -> str:
    return f"{_PREFIXE}:{empreinte(str(user_id), secret)}:{fenetre_jour()}"


async def autoriser_analyse_cv(
    cache: CacheRedis, *, user_id: int, par_jour: int, secret: str
) -> None:
    """Consomme une place du quota du jour, ou lève `TropDAnalyses`.

    Appelée AVANT tout travail : refuser après avoir extrait le texte serait du
    calcul payé pour rien, et refuser après l'appel LLM serait de l'argent perdu.
    """
    cle = _cle(user_id, secret)
    if await incrementer(cache, cle, _UN_JOUR) > par_jour:
        raise TropDAnalyses


async def liberer_analyse_cv(cache: CacheRedis, *, user_id: int, secret: str) -> None:
    """Rend la place prise par `autoriser_analyse_cv` (§9).

    À n'appeler que quand RIEN n'a été payé : DeepSeek injoignable. Une analyse
    qui a coûté de l'argent puis échoué (`CvIllisible` après relance) garde sa
    place consommée.

    Ne descend jamais sous zéro : si la clé du jour a expiré ou changé de jour
    entre le dépôt et l'échec, un `decr` aveugle créerait un compteur négatif,
    c'est-à-dire des analyses gratuites offertes à l'utilisateur.
    """
    cle = _cle(user_id, secret)
    if await cache.decr(cle) < 0:
        await cache.incr(cle)
