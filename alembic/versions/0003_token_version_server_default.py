"""token_version : rétablir le défaut serveur

`users.token_version` a perdu son `server_default` dans la migration 0002 :
« le défaut serveur n'était là que pour remplir les lignes existantes ; la
valeur vient du modèle SQLAlchemy ensuite. » C'était une erreur (revue finale
de la Phase 2, corrections mineures) : un INSERT hors ORM (script ad hoc,
migration de données future) violerait `NOT NULL` faute de valeur, plutôt que
d'hériter silencieusement de 0 comme le fait cette migration.

`language` et `state` (`src/db/models.py`) n'offrent PAS cette protection :
vérifié en base (`information_schema.columns.column_default` est vide pour
les deux), leur défaut n'existe que côté modèle SQLAlchemy (`default=`), pas
en base. Un INSERT hors ORM omettant `language` ou `state` violerait donc
`NOT NULL` exactement comme `token_version` avant cette migration — ce n'est
pas corrigé ici, seule `token_version` l'est, faute d'un besoin identifié
pour les deux autres à ce jour.

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
