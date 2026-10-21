"""Plafond d'analyses de CV par utilisateur et par jour.

Le §13 du CLAUDE.md exige un test pour toute règle de quota. Celle-ci est aussi
un plafond de COÛT : chaque analyse est un appel payé à DeepSeek.
"""

from __future__ import annotations

import pytest

from src.core.cv_limites import autoriser_analyse_cv, liberer_analyse_cv
from src.core.erreurs import TropDAnalyses
from tests.conftest import FauxCache

SECRET = "secret-de-test"


async def test_autorise_jusquau_plafond() -> None:
    cache = FauxCache()
    for _ in range(3):
        await autoriser_analyse_cv(cache, user_id=1, par_jour=3, secret=SECRET)


async def test_refuse_au_dela_du_plafond() -> None:
    cache = FauxCache()
    for _ in range(3):
        await autoriser_analyse_cv(cache, user_id=1, par_jour=3, secret=SECRET)
    with pytest.raises(TropDAnalyses):
        await autoriser_analyse_cv(cache, user_id=1, par_jour=3, secret=SECRET)


async def test_les_utilisateurs_ne_partagent_pas_leur_plafond() -> None:
    """Sinon le premier inscrit du jour bloquerait tous les autres — c'est
    exactement la panne silencieuse trouvée en Phase 2 sur les plafonds par IP."""
    cache = FauxCache()
    for _ in range(3):
        await autoriser_analyse_cv(cache, user_id=1, par_jour=3, secret=SECRET)
    await autoriser_analyse_cv(cache, user_id=2, par_jour=3, secret=SECRET)


async def test_la_cle_redis_ne_porte_pas_lidentifiant_en_clair() -> None:
    """Même convention que les plafonds d'authentification : la clé est une
    empreinte, pour qu'un dump Redis ne soit pas un annuaire."""
    cache = FauxCache()
    await autoriser_analyse_cv(cache, user_id=4242, par_jour=3, secret=SECRET)
    assert cache.valeurs
    assert all("4242" not in cle for cle in cache.valeurs)


async def test_le_compteur_expire_au_bout_dun_jour() -> None:
    """Sans TTL, le plafond du jour deviendrait un plafond à vie."""
    cache = FauxCache()
    await autoriser_analyse_cv(cache, user_id=1, par_jour=3, secret=SECRET)
    assert list(cache.ttl.values()) == [86_400]


async def test_liberer_rend_la_place() -> None:
    cache = FauxCache()
    for _ in range(3):
        await autoriser_analyse_cv(cache, user_id=1, par_jour=3, secret=SECRET)
    await liberer_analyse_cv(cache, user_id=1, secret=SECRET)
    await autoriser_analyse_cv(cache, user_id=1, par_jour=3, secret=SECRET)


async def test_liberer_sans_compteur_ne_descend_pas_sous_zero() -> None:
    """Clé expirée ou changement de jour : un compteur négatif offrirait des
    analyses gratuites."""
    cache = FauxCache()
    await liberer_analyse_cv(cache, user_id=1, secret=SECRET)
    for _ in range(3):
        await autoriser_analyse_cv(cache, user_id=1, par_jour=3, secret=SECRET)
    with pytest.raises(TropDAnalyses):
        await autoriser_analyse_cv(cache, user_id=1, par_jour=3, secret=SECRET)
