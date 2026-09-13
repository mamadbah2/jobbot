"""identite par email

Le 2026-09-11, `users.email` devient l'identité de connexion et `telegram_id`
n'est plus qu'un canal parmi d'autres (CLAUDE.md §2 et §5).

La table était VIDE au moment d'écrire cette migration (0 ligne, vérifié le
2026-09-11) : aucun backfill n'est donc nécessaire. Sur une table peuplée,
`nullable=False` sur `email` et `phone` échouerait — c'est voulu, mieux vaut
un échec bruyant qu'une adresse inventée.

Revision ID: a1c2e3f40002
Revises: 4bfafb92720f
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "a1c2e3f40002"
down_revision: str | None = "4bfafb92720f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column("users", "telegram_id", existing_type=sa.BigInteger(), nullable=True)
    op.alter_column("users", "email", existing_type=sa.String(length=320), nullable=False)
    op.alter_column("users", "phone", existing_type=sa.String(length=32), nullable=False)
    op.create_index(op.f("ix_users_email"), "users", ["email"], unique=True)
    op.create_index(op.f("ix_users_phone"), "users", ["phone"], unique=True)
    op.add_column(
        "users",
        sa.Column("token_version", sa.Integer(), server_default="0", nullable=False),
    )
    # Le défaut serveur n'était là que pour remplir les lignes existantes ;
    # la valeur vient du modèle SQLAlchemy ensuite.
    op.alter_column("users", "token_version", server_default=None)


def downgrade() -> None:
    op.drop_column("users", "token_version")
    op.drop_index(op.f("ix_users_phone"), table_name="users")
    op.drop_index(op.f("ix_users_email"), table_name="users")
    op.alter_column("users", "phone", existing_type=sa.String(length=32), nullable=True)
    op.alter_column("users", "email", existing_type=sa.String(length=320), nullable=True)
    op.alter_column("users", "telegram_id", existing_type=sa.BigInteger(), nullable=False)
