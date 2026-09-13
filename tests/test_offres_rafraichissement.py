"""Le rafraîchissement déclenché par une visite ne doit pas survivre à la
fermeture du client Redis de la requête (spec du client web §7).

Note sur le planificateur utilisé ici : on ferme chaque coroutine **sans
jamais la démarrer** (motif déjà en place dans `tests/test_fraicheur.py`,
au test `test_aucune_passe_planifiee_si_la_base_est_fraiche`). Un
planificateur à base de `asyncio.ensure_future` démarrerait réellement la
coroutine — celle-ci atteindrait `construire_client` puis
`async with session_scope()`, donc la base — avant qu'un `cancel()` ne
prenne effet. `tests/conftest.py` est explicite : « Aucun test unitaire ne
doit toucher au réseau ni à la base ». Le chemin d'exécution réel d'une
passe est déjà couvert par `tests/test_fraicheur.py` ; ici on ne teste que
la planification.
"""

from __future__ import annotations

from collections.abc import Coroutine
from typing import Any

from src.worker_ingest import rafraichir_a_la_demande
from tests.conftest import FauxCache


async def test_rafraichir_a_la_demande_accepte_un_planificateur() -> None:
    """Sans ce paramètre, l'API ne peut pas savoir quand la passe est finie,
    donc ne peut pas fermer son client Redis au bon moment."""
    cache = FauxCache()
    planifiees: list[Coroutine[Any, Any, None]] = []

    decisions = await rafraichir_a_la_demande(cache, planifier=planifiees.append)

    assert decisions, "au moins une source doit être décidée"
    # On ferme sans jamais démarrer : voir la note en tête de fichier.
    for coro in planifiees:
        coro.close()


async def test_une_seconde_visite_immediate_ne_relance_rien() -> None:
    """Le verrou et l'horodatage de dernière passe font leur travail."""
    cache = FauxCache()
    planifiees: list[Coroutine[Any, Any, None]] = []

    await rafraichir_a_la_demande(cache, planifier=planifiees.append)
    premier_lot = len(planifiees)
    await rafraichir_a_la_demande(cache, planifier=planifiees.append)

    assert len(planifiees) == premier_lot, "la seconde visite ne doit rien replanifier"
    for coro in planifiees:
        coro.close()
