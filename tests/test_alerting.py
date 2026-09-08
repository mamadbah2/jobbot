"""Alerte administrateur (CLAUDE.md §7 : « ne jamais échouer en silence »).

`ADMIN_TELEGRAM_ID` n'est pas encore fourni par le porteur du projet : le
code doit rester correct à 0, c'est-à-dire signaler bruyamment plutôt que
planter ou se taire.
"""

from __future__ import annotations

import pytest
from structlog.testing import capture_logs

from src.alerting import AlerteJournalisee, construire_alerte
from src.config import get_settings


async def test_journalise_l_alerte_en_erreur() -> None:
    with capture_logs() as journal:
        await AlerteJournalisee(admin_telegram_id=42).envoyer("scraper_casse", source="x")
    (evenement,) = journal
    assert evenement["log_level"] == "error"
    assert evenement["alerte"] == "scraper_casse"
    assert evenement["source"] == "x"
    assert evenement["destinataire"] == "42"


async def test_sans_destinataire_configure_l_alerte_ne_plante_pas() -> None:
    """§14 : tant que l'admin n'a pas donné son identifiant, on ne peut que logger."""
    with capture_logs() as journal:
        await AlerteJournalisee(admin_telegram_id=0).envoyer("scraper_casse", source="x")
    (evenement,) = journal
    assert evenement["log_level"] == "error"
    assert evenement["destinataire"] == "absent"


def test_la_fabrique_lit_la_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ADMIN_TELEGRAM_ID", "12345")
    get_settings.cache_clear()
    alerte = construire_alerte(get_settings())
    assert isinstance(alerte, AlerteJournalisee)
    assert alerte.admin_telegram_id == 12345
