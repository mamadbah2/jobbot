"""Garde-fous de l'envoi (spec Phase 2 §10).

L'endpoint est public : sans ces limites, on inonde l'adresse d'un tiers et on
brûle la réputation du futur domaine d'envoi.
"""

from __future__ import annotations

from typing import Any

import pytest

from src.core.auth.limites import ReglesEnvoi, autoriser_envoi
from src.core.erreurs import PlafondGlobalAtteint, TropDeDemandes
from tests.conftest import FauxCache

SECRET = "secret_de_test"
ADRESSE = "fatou@example.sn"
IP = "41.82.0.1"

REGLES = ReglesEnvoi(
    cooldown_secondes=60, par_heure=3, par_jour=10, par_ip_heure=10, plafond_global_jour=500
)


class AlerteEspion:
    def __init__(self) -> None:
        self.recues: list[tuple[str, dict[str, Any]]] = []

    async def envoyer(self, evenement: str, **contexte: Any) -> None:
        self.recues.append((evenement, contexte))


async def demander(cache: FauxCache, alerte: AlerteEspion, regles: ReglesEnvoi = REGLES) -> None:
    await autoriser_envoi(
        cache, adresse=ADRESSE, ip=IP, regles=regles, secret=SECRET, alerte=alerte
    )


async def test_premier_envoi_autorise(faux_cache: FauxCache) -> None:
    await demander(faux_cache, AlerteEspion())


async def test_cooldown_bloque_le_second_envoi_immediat(faux_cache: FauxCache) -> None:
    alerte = AlerteEspion()
    await demander(faux_cache, alerte)
    with pytest.raises(TropDeDemandes) as info:
        await demander(faux_cache, alerte)
    assert info.value.attendre_secondes == 60


async def test_plafond_horaire_par_adresse(faux_cache: FauxCache) -> None:
    alerte = AlerteEspion()
    regles = ReglesEnvoi(
        cooldown_secondes=0, par_heure=3, par_jour=10, par_ip_heure=100, plafond_global_jour=500
    )
    for _ in range(3):
        await demander(faux_cache, alerte, regles)
    with pytest.raises(TropDeDemandes):
        await demander(faux_cache, alerte, regles)


async def test_plafond_journalier_par_adresse(faux_cache: FauxCache) -> None:
    alerte = AlerteEspion()
    regles = ReglesEnvoi(
        cooldown_secondes=0, par_heure=100, par_jour=10, par_ip_heure=100, plafond_global_jour=500
    )
    for _ in range(10):
        await demander(faux_cache, alerte, regles)
    with pytest.raises(TropDeDemandes):
        await demander(faux_cache, alerte, regles)


async def test_plafond_par_ip_independant_de_l_adresse(faux_cache: FauxCache) -> None:
    """Changer d'adresse ne doit pas remettre le compteur d'IP à zéro."""
    alerte = AlerteEspion()
    regles = ReglesEnvoi(
        cooldown_secondes=0, par_heure=100, par_jour=100, par_ip_heure=2, plafond_global_jour=500
    )
    for i in range(2):
        await autoriser_envoi(
            faux_cache, adresse=f"u{i}@example.sn", ip=IP, regles=regles, secret=SECRET,
            alerte=alerte,
        )
    with pytest.raises(TropDeDemandes):
        await autoriser_envoi(
            faux_cache, adresse="autre@example.sn", ip=IP, regles=regles, secret=SECRET,
            alerte=alerte,
        )


async def test_plafond_global_leve_et_alerte(faux_cache: FauxCache) -> None:
    """« Ne jamais échouer en silence » (CLAUDE.md §7)."""
    alerte = AlerteEspion()
    regles = ReglesEnvoi(
        cooldown_secondes=0, par_heure=100, par_jour=100, par_ip_heure=100, plafond_global_jour=2
    )
    for i in range(2):
        await autoriser_envoi(
            faux_cache, adresse=f"u{i}@example.sn", ip=f"41.82.0.{i}", regles=regles,
            secret=SECRET, alerte=alerte,
        )
    with pytest.raises(PlafondGlobalAtteint):
        await autoriser_envoi(
            faux_cache, adresse="trop@example.sn", ip="41.82.0.9", regles=regles,
            secret=SECRET, alerte=alerte,
        )
    assert [nom for nom, _ in alerte.recues] == ["plafond_global_envois_atteint"]


async def test_l_adresse_n_apparait_pas_en_clair_dans_les_cles(faux_cache: FauxCache) -> None:
    await demander(faux_cache, AlerteEspion())
    assert ADRESSE not in "".join(faux_cache.valeurs.keys())


async def test_le_plafond_global_n_est_pas_consomme_par_un_refus(faux_cache: FauxCache) -> None:
    """Un attaquant arrêté par SA limite ne doit pas entamer celle de tout le monde."""
    alerte = AlerteEspion()
    regles = ReglesEnvoi(
        cooldown_secondes=60, par_heure=3, par_jour=10, par_ip_heure=100, plafond_global_jour=500
    )
    await demander(faux_cache, alerte, regles)
    with pytest.raises(TropDeDemandes):
        await demander(faux_cache, alerte, regles)
    cle_globale = next(c for c in faux_cache.valeurs if "global" in c)
    assert faux_cache.valeurs[cle_globale] == "1"
