"""Primitives de comptage à fenêtre fixe : le rôle de `NX` sur le TTL."""

from __future__ import annotations

from src.core.limites import incrementer
from tests.conftest import FauxCache

CLE = "jobbot:test:compteur"


async def test_un_compteur_sans_ttl_est_repare() -> None:
    """Simule un processus mort entre `incr` et `expire` : la clé existe, sans
    TTL. Sans auto-réparation, elle serait éternelle et la cible bloquée à vie."""
    cache = FauxCache()
    cache.valeurs[CLE] = "5"
    assert CLE not in cache.ttl

    assert await incrementer(cache, CLE, 3600) == 6
    assert cache.ttl[CLE] == 3600


async def test_le_ttl_dune_fenetre_en_cours_nest_pas_reecrit() -> None:
    """Sans `NX`, chaque requête rallongerait la fenêtre : un plafond horaire
    deviendrait glissant à l'infini."""
    cache = FauxCache()
    await incrementer(cache, CLE, 3600)
    cache.ttl[CLE] = 1200  # la fenêtre est à moitié écoulée

    await incrementer(cache, CLE, 3600)
    assert cache.ttl[CLE] == 1200
