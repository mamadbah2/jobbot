"""Envoi du code (spec Phase 2 §7)."""

from __future__ import annotations

import pytest
from structlog.testing import capture_logs

from src.config import get_settings
from src.courriel.console import CourrielConsole
from src.courriel.provider import construire_fournisseur


async def test_le_fournisseur_console_journalise_le_code() -> None:
    with capture_logs() as journal:
        await CourrielConsole().envoyer_code("fatou@example.sn", "123456")
    assert any(e.get("code") == "123456" for e in journal)
    assert any(e.get("destinataire") == "fatou@example.sn" for e in journal)


async def test_le_fournisseur_console_previent_qu_il_n_envoie_rien() -> None:
    """Personne ne doit croire qu'un email est parti (CLAUDE.md §7)."""
    with capture_logs() as journal:
        await CourrielConsole().envoyer_code("fatou@example.sn", "123456")
    assert any(e.get("event") == "courriel_non_envoye_mode_console" for e in journal)


def test_console_est_le_defaut() -> None:
    assert isinstance(construire_fournisseur(get_settings()), CourrielConsole)


def test_fournisseur_inconnu_refuse(monkeypatch: pytest.MonkeyPatch) -> None:
    """Un nom mal orthographié ne doit pas retomber silencieusement sur console."""
    monkeypatch.setenv("FOURNISSEUR_COURRIEL", "resendd")
    get_settings.cache_clear()
    with pytest.raises(ValueError):
        construire_fournisseur(get_settings())
