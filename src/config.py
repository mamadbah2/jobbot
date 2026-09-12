"""Configuration applicative — tout vient de l'environnement (CLAUDE.md §3).

Aucun secret en dur, aucune valeur métier codée en dur : les plafonds du §6 et du §8
sont des variables d'environnement pour pouvoir être ajustés sans redéploiement de code.
"""

from __future__ import annotations

import secrets
from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, model_validator
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

    # --- PostgreSQL ---
    postgres_host: str = "postgres"
    postgres_port: int = 5432
    postgres_user: str = "jobbot"
    postgres_password: SecretStr = SecretStr("jobbot_dev_password")
    postgres_db: str = "jobbot"

    # --- Redis ---
    redis_url: str = "redis://redis:6379/0"

    # --- Authentification (spec Phase 2, §5 et §10) ---
    # Vide autorisé en dev seulement : voir le validateur plus bas.
    jwt_secret: SecretStr = SecretStr("")
    jwt_duree_jours: int = Field(default=30, ge=1)
    cookie_session_nom: str = "jobbot_session"

    # Le code vit en Redis, haché, et expire tout seul (§2, interdiction n°2).
    code_ttl_secondes: int = Field(default=300, ge=60)

    # Garde-fous de l'envoi. L'endpoint est public : non protégé, il permet
    # d'inonder l'adresse d'un tiers et de brûler la réputation du domaine (§7).
    auth_cooldown_secondes: int = Field(default=60, ge=0)
    auth_envois_par_heure: int = Field(default=3, ge=1)
    auth_envois_par_jour: int = Field(default=10, ge=1)
    auth_envois_par_ip_heure: int = Field(default=10, ge=1)
    auth_plafond_global_jour: int = Field(default=500, ge=1)

    # Plafonds de /auth/code/verifie (pas de cooldown : un utilisateur qui se
    # trompe de chiffre doit pouvoir recommencer tout de suite). C'est la
    # SEULE protection contre la force brute : `codes.verifier` ne détruit
    # plus le code sur échec (voir `src/core/auth/codes.py` pour pourquoi).
    auth_verifications_par_heure: int = Field(default=20, ge=1)
    auth_verifications_par_ip_heure: int = Field(default=60, ge=1)

    fournisseur_courriel: str = "console"

    # Destinataire des alertes d'exploitation (scraper cassé, plafond global
    # atteint, coût LLM). Vide = alertes journalisées seulement : un état
    # dégradé mais fonctionnel, contrairement à FOURNISSEUR_COURRIEL=console
    # qui est un trou de sécurité et fait échouer le démarrage en prod.
    admin_courriel: str = ""

    # Adresses du reverse proxy autorisées à renseigner X-Forwarded-For.
    # Vide par défaut = on ne fait confiance à personne et `request.client.host`
    # reste l'adresse de la connexion. À renseigner le jour où un proxy existe :
    # sans cela le plafond par IP compterait tous les utilisateurs ensemble ;
    # avec une valeur trop large, n'importe qui pourrait usurper son IP.
    proxy_ips_de_confiance: str = ""

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

    @property
    def cookie_session_secure(self) -> bool:
        """Cookie `Secure` en production ; en dev on travaille en HTTP."""
        return self.is_prod

    @model_validator(mode="after")
    def _exiger_un_secret_en_prod(self) -> Settings:
        """En prod, un secret vide ou trop court permettrait de forger un jeton
        (ou, dès la tâche 5, un code de vérification ou une clé de limitation :
        les trois usages dérivent tous du même `JWT_SECRET`, cf. `core/auth/cles.py`)."""
        valeur = self.jwt_secret.get_secret_value()
        if not valeur:
            if self.is_prod:
                raise ValueError(
                    "JWT_SECRET est obligatoire en production. "
                    "Générez-le avec : "
                    "python -c 'import secrets; print(secrets.token_urlsafe(48))'"
                )
            # En dev, un secret éphémère : les jetons ne survivent pas à un
            # redémarrage, ce qui est sans conséquence et évite un secret par
            # défaut publiquement connu.
            object.__setattr__(self, "jwt_secret", SecretStr(secrets.token_urlsafe(48)))
            return self
        if self.is_prod and len(valeur) < 32:
            raise ValueError(
                "JWT_SECRET doit contenir au moins 32 caractères en production, "
                "faute de quoi il est trop facile à retrouver par force brute. "
                "Générez-en un avec : "
                "python -c 'import secrets; print(secrets.token_urlsafe(48))'"
            )
        return self

    @model_validator(mode="after")
    def _interdire_le_fournisseur_console_en_prod(self) -> Settings:
        """`console` écrit le code de vérification dans les logs en clair
        (`src/courriel/console.py`) : quiconque lit les logs peut ouvrir
        n'importe quelle session. C'est la valeur par défaut, donc rien ne
        l'empêchait auparavant de partir en production par simple oubli."""
        if self.is_prod and self.fournisseur_courriel == "console":
            raise ValueError(
                "FOURNISSEUR_COURRIEL=console est interdit en production : le code "
                "de vérification part en clair dans les logs, ce qui permet "
                "d'ouvrir n'importe quelle session. Configurez un fournisseur "
                "d'envoi réel avant de déployer."
            )
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Instance unique, mise en cache. Les tests appellent `get_settings.cache_clear()`."""
    return Settings()  # type: ignore[call-arg]  # les champs viennent de l'environnement
