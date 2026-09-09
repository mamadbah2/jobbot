"""Configuration applicative — tout vient de l'environnement (CLAUDE.md §3).

Aucun secret en dur, aucune valeur métier codée en dur : les plafonds du §6 et du §8
sont des variables d'environnement pour pouvoir être ajustés sans redéploiement de code.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

Environment = Literal["dev", "prod"]
TelegramMode = Literal["polling", "webhook"]


class Settings(BaseSettings):
    """Réglages du projet, chargés depuis l'environnement ou un fichier .env."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- Général ---
    environment: Environment = "dev"
    log_level: str = "INFO"

    # --- Telegram ---
    telegram_bot_token: SecretStr
    telegram_mode: TelegramMode = "polling"
    # Volontairement court : le FAI local coupe api.telegram.org par intermittence
    # et un long-poll de 30 s expire côté client avant côté serveur (CLAUDE.md §15).
    telegram_long_poll_timeout: int = Field(default=2, ge=1, le=50)
    telegram_webhook_url: str = ""
    telegram_webhook_secret: SecretStr = SecretStr("")
    admin_telegram_id: int = 0

    # --- PostgreSQL ---
    postgres_host: str = "postgres"
    postgres_port: int = 5432
    postgres_user: str = "jobbot"
    postgres_password: SecretStr = SecretStr("jobbot_dev_password")
    postgres_db: str = "jobbot"

    # --- Redis ---
    redis_url: str = "redis://redis:6379/0"

    # --- Serveur HTTP (healthcheck, puis webhook de paiement en §10) ---
    http_host: str = "0.0.0.0"  # noqa: S104 — écoute dans le conteneur, exposée par compose
    http_port: int = 8080

    # --- Règles métier (CLAUDE.md §6 et §8) ---
    pro_monthly_quota: int = Field(default=25, ge=1)
    free_trial_applications: int = Field(default=2, ge=0)
    free_daily_alerts: int = Field(default=5, ge=0)
    subscription_price_fcfa: int = Field(default=1000, ge=0)
    subscription_days: int = Field(default=30, ge=1)
    grace_period_days: int = Field(default=3, ge=0)
    max_applications_per_job: int = Field(default=15, ge=1)

    # --- Scraping (CLAUDE.md §2, interdiction n°4) ---
    # Rafraîchissement à la demande, déclenché par une visite (§7).
    # La fraîcheur se mesure à la dernière passe RÉUSSIE, pas à la date de la
    # dernière offre : sinon un jour sans publication relance une passe à
    # chaque visite. Le verrou garantit une seule passe concurrente (§2.4).
    ingest_fraicheur_minutes: int = Field(default=30, ge=1)
    ingest_verrou_secondes: int = Field(default=600, ge=60)

    scraper_user_agent: str = "JobBotSN/0.1 (+contact: admin@example.sn)"
    scraper_delay_seconds: float = Field(default=4.0, ge=3.0)

    # Volontairement une property et NON un `computed_field` : un computed_field
    # entre dans `repr()` et dans `model_dump()`, ce qui ferait fuiter le mot de
    # passe Postgres dans les logs (CLAUDE.md §13).
    @property
    def database_url(self) -> str:
        """DSN SQLAlchemy async (driver asyncpg)."""
        pwd = self.postgres_password.get_secret_value()
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{pwd}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def is_prod(self) -> bool:
        return self.environment == "prod"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Instance unique, mise en cache. Les tests appellent `get_settings.cache_clear()`."""
    return Settings()  # type: ignore[call-arg]  # les champs viennent de l'environnement
