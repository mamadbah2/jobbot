"""Config : valeurs par défaut, surcharges d'environnement, DSN."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.config import Settings, get_settings


def test_token_obligatoire(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    get_settings.cache_clear()
    with pytest.raises(ValidationError):
        Settings()  # type: ignore[call-arg]


def test_defauts_metier() -> None:
    """Les plafonds du §6 et du §8 ont les valeurs du brief par défaut."""
    s = get_settings()
    assert s.pro_monthly_quota == 25
    assert s.free_trial_applications == 2
    assert s.free_daily_alerts == 5
    assert s.subscription_price_fcfa == 1000
    assert s.subscription_days == 30
    assert s.grace_period_days == 3
    assert s.max_applications_per_job == 15


def test_quota_surchargeable_par_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """§6 : le quota Pro est un plafond de coût, il doit être configurable."""
    monkeypatch.setenv("PRO_MONTHLY_QUOTA", "40")
    get_settings.cache_clear()
    assert get_settings().pro_monthly_quota == 40


def test_delai_scraping_minimum(monkeypatch: pytest.MonkeyPatch) -> None:
    """§2, interdiction n°4 : jamais moins de 3 s entre deux requêtes."""
    monkeypatch.setenv("SCRAPER_DELAY_SECONDS", "0.5")
    get_settings.cache_clear()
    with pytest.raises(ValidationError):
        get_settings()


def test_database_url_utilise_asyncpg(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("POSTGRES_USER", "u")
    monkeypatch.setenv("POSTGRES_PASSWORD", "p")
    monkeypatch.setenv("POSTGRES_HOST", "h")
    monkeypatch.setenv("POSTGRES_PORT", "5433")
    monkeypatch.setenv("POSTGRES_DB", "d")
    get_settings.cache_clear()
    assert get_settings().database_url == "postgresql+asyncpg://u:p@h:5433/d"


def test_secrets_non_exposes_dans_repr() -> None:
    """Aucun secret ne doit fuiter dans les logs via un repr de config."""
    s = get_settings()
    assert "TOKEN_DE_TEST" not in repr(s)
    assert "motdepasse_test" not in repr(s)
