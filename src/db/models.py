"""Modèle de données (CLAUDE.md §5).

Conventions :
- champs à valeurs contraintes = VARCHAR + CHECK, pas d'ENUM natif Postgres
  (ajouter une valeur à un ENUM natif impose une migration bloquante) ;
- toutes les dates en UTC (TIMESTAMPTZ) ;
- les tables sont créées par Alembic uniquement, jamais par `create_all` (§5).
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Final

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

# --- Valeurs autorisées, référencées par les contraintes CHECK ---------------

USER_STATES: Final = ("onboarding", "active", "blocked")
PLANS: Final = ("free", "pro")
SUBSCRIPTION_STATUSES: Final = ("active", "expired", "pending")
APPLY_METHODS: Final = ("email", "form", "external")
APPLICATION_STATUSES: Final = ("draft", "sent", "failed", "bounced")


def _check_in(column: str, values: tuple[str, ...], name: str) -> CheckConstraint:
    """Contrainte « valeur parmi »."""
    allowed = ", ".join(f"'{v}'" for v in values)
    return CheckConstraint(f"{column} IN ({allowed})", name=name)


class Base(DeclarativeBase):
    """Base déclarative commune."""


class TimestampMixin:
    """Horodatage de création, en UTC côté serveur."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


# --- Tables -----------------------------------------------------------------


class User(TimestampMixin, Base):
    __tablename__ = "users"
    __table_args__ = (_check_in("state", USER_STATES, "ck_users_state"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False, index=True)
    phone: Mapped[str | None] = mapped_column(String(32))
    full_name: Mapped[str | None] = mapped_column(String(255))
    # Nullable : déduit du CV en Phase 2, confirmé par l'utilisateur avant le
    # premier envoi car il sert de Reply-To (CLAUDE.md §7 et §14.5).
    email: Mapped[str | None] = mapped_column(String(320))
    language: Mapped[str] = mapped_column(String(8), default="fr", nullable=False)
    state: Mapped[str] = mapped_column(String(16), default="onboarding", nullable=False)

    profile: Mapped[Profile | None] = relationship(back_populates="user", uselist=False)


class Profile(Base):
    __tablename__ = "profiles"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    raw_cv_text: Mapped[str | None] = mapped_column(Text)
    # expériences, formations, compétences, langues, secteurs visés, mobilité,
    # prétention salariale. Sert de source de vérité au post-contrôle anti-invention (§8.5).
    structured: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    cv_file_path: Mapped[str | None] = mapped_column(String(512))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    user: Mapped[User] = relationship(back_populates="profile")


class Subscription(Base):
    __tablename__ = "subscriptions"
    __table_args__ = (
        _check_in("plan", PLANS, "ck_subscriptions_plan"),
        _check_in("status", SUBSCRIPTION_STATUSES, "ck_subscriptions_status"),
        # Idempotence du webhook de paiement (§10) : un même provider_ref traité
        # deux fois ne peut pas créer deux abonnements.
        UniqueConstraint("provider_ref", name="uq_subscriptions_provider_ref"),
        Index("ix_subscriptions_expires_at", "expires_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    plan: Mapped[str] = mapped_column(String(8), default="free", nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="pending", nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    provider_ref: Mapped[str | None] = mapped_column(String(128))
    amount_fcfa: Mapped[int | None] = mapped_column(Integer)


class Job(Base):
    __tablename__ = "jobs"
    __table_args__ = (
        _check_in("apply_method", APPLY_METHODS, "ck_jobs_apply_method"),
        UniqueConstraint("source", "source_id", name="uq_jobs_source_source_id"),
        Index("ix_jobs_fingerprint", "fingerprint"),
        Index("ix_jobs_posted_at", "posted_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    source_id: Mapped[str] = mapped_column(String(255), nullable=False)
    url: Mapped[str] = mapped_column(String(1024), unique=True, nullable=False)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    company: Mapped[str | None] = mapped_column(String(255))
    location: Mapped[str | None] = mapped_column(String(255))
    contract_type: Mapped[str | None] = mapped_column(String(64))
    description: Mapped[str | None] = mapped_column(Text)
    # Renseigné seulement si un email valide a été extrait de la description (§7).
    apply_email: Mapped[str | None] = mapped_column(String(320))
    apply_method: Mapped[str] = mapped_column(String(16), default="form", nullable=False)
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    raw: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Application(Base):
    __tablename__ = "applications"
    __table_args__ = (
        _check_in("status", APPLICATION_STATUSES, "ck_applications_status"),
        # Un utilisateur ne postule qu'une fois par offre (§5).
        UniqueConstraint("user_id", "job_id", name="uq_applications_user_job"),
        Index("ix_applications_user_id", "user_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="draft", nullable=False)
    cv_path: Mapped[str | None] = mapped_column(String(512))
    letter_path: Mapped[str | None] = mapped_column(String(512))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Variante de lettre retenue, choisie par hash(user_id + job_id) % n (§8.1).
    template_variant: Mapped[int | None] = mapped_column(Integer)
    llm_cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(10, 6))
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class UsageCounter(Base):
    __tablename__ = "usage_counters"
    __table_args__ = (UniqueConstraint("user_id", "period", name="uq_usage_counters_user_period"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    period: Mapped[str] = mapped_column(String(7), nullable=False)  # AAAA-MM
    applications_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    llm_tokens_in: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    llm_tokens_out: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    cost_usd: Mapped[Decimal] = mapped_column(Numeric(12, 6), default=Decimal("0"), nullable=False)


class JobApplicationStat(Base):
    """Compteur de candidatures par offre — plafond anti-saturation (§8.3)."""

    __tablename__ = "job_application_stats"

    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), primary_key=True)
    count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
