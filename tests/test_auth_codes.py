"""Codes de vérification (spec Phase 2 §5 : jamais en base, jamais dans les logs)."""

from __future__ import annotations

import pytest

from src.core.auth import codes
from src.core.erreurs import CodeExpire, CodeInvalide
from tests.conftest import FauxCache

SECRET = "secret_de_test"
ADRESSE = "fatou@example.sn"


def test_code_a_six_chiffres() -> None:
    for _ in range(200):
        code = codes.generer_code()
        assert len(code) == 6
        assert code.isdigit()


def test_codes_successifs_differents() -> None:
    """Un code prévisible rendrait la vérification inutile."""
    tires = {codes.generer_code() for _ in range(200)}
    assert len(tires) > 150


async def test_depot_puis_verification_reussie(faux_cache: FauxCache) -> None:
    await codes.deposer(faux_cache, ADRESSE, "123456", secret=SECRET, ttl_secondes=300)
    await codes.verifier(faux_cache, ADRESSE, "123456", secret=SECRET, essais_max=5)


async def test_le_code_en_clair_n_est_jamais_stocke(faux_cache: FauxCache) -> None:
    await codes.deposer(faux_cache, ADRESSE, "123456", secret=SECRET, ttl_secondes=300)
    contenu = "".join(faux_cache.valeurs.keys()) + "".join(faux_cache.valeurs.values())
    assert "123456" not in contenu
    assert ADRESSE not in contenu


async def test_mauvais_code_refuse(faux_cache: FauxCache) -> None:
    await codes.deposer(faux_cache, ADRESSE, "123456", secret=SECRET, ttl_secondes=300)
    with pytest.raises(CodeInvalide):
        await codes.verifier(faux_cache, ADRESSE, "000000", secret=SECRET, essais_max=5)


async def test_aucun_code_depose(faux_cache: FauxCache) -> None:
    with pytest.raises(CodeExpire):
        await codes.verifier(faux_cache, ADRESSE, "123456", secret=SECRET, essais_max=5)


async def test_code_detruit_apres_cinq_essais(faux_cache: FauxCache) -> None:
    await codes.deposer(faux_cache, ADRESSE, "123456", secret=SECRET, ttl_secondes=300)
    for _ in range(5):
        with pytest.raises(CodeInvalide):
            await codes.verifier(faux_cache, ADRESSE, "000000", secret=SECRET, essais_max=5)
    # Le bon code ne doit plus marcher : le code a été détruit, pas seulement compté.
    with pytest.raises(CodeExpire):
        await codes.verifier(faux_cache, ADRESSE, "123456", secret=SECRET, essais_max=5)


async def test_code_consomme_apres_succes(faux_cache: FauxCache) -> None:
    """Un code doit être à usage unique."""
    await codes.deposer(faux_cache, ADRESSE, "123456", secret=SECRET, ttl_secondes=300)
    await codes.verifier(faux_cache, ADRESSE, "123456", secret=SECRET, essais_max=5)
    with pytest.raises(CodeExpire):
        await codes.verifier(faux_cache, ADRESSE, "123456", secret=SECRET, essais_max=5)


async def test_deux_adresses_ne_se_melangent_pas(faux_cache: FauxCache) -> None:
    await codes.deposer(faux_cache, "a@example.sn", "111111", secret=SECRET, ttl_secondes=300)
    await codes.deposer(faux_cache, "b@example.sn", "222222", secret=SECRET, ttl_secondes=300)
    with pytest.raises(CodeInvalide):
        await codes.verifier(faux_cache, "a@example.sn", "222222", secret=SECRET, essais_max=5)
    await codes.verifier(faux_cache, "b@example.sn", "222222", secret=SECRET, essais_max=5)
