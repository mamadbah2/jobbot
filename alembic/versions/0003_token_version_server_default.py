"""token_version : rétablir le défaut serveur

`users.token_version` a perdu son `server_default` dans la migration 0002 :
« le défaut serveur n'était là que pour remplir les lignes existantes ; la
valeur vient du modèle SQLAlchemy ensuite. » C'était une erreur (revue finale
de la Phase 2, corrections mineures) : un INSERT hors ORM (script ad hoc,
migration de données future) violerait `NOT NULL` au lieu d'hériter
silencieusement de 0, comme n'importe quelle autre colonne à défaut de ce
fichier (`language`, `state`).

Revision ID: a1c2e3f40003
Revises: a1c2e3f40002
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "a1c2e3f40003"
down_revision: str | None = "a1c2e3f40002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column("users", "token_version", server_default="0")


def downgrade() -> None:
    op.alter_column("users", "token_version", server_default=None)
