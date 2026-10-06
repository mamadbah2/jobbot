"""États de parsing du profil, et retrait de cv_file_path.

Le fichier d'origine n'est jamais conservé (décision du 2026-10-01) : la colonne
resterait vide à jamais. Elle n'a jamais été écrite par aucun code, donc la
supprimer ne perd aucune donnée — vérifié avant d'écrire cette migration.

Revision ID: a1c2e3f40006
Revises: a1c2e3f40005
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "a1c2e3f40006"
down_revision: str | None = "a1c2e3f40005"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    # server_default sur l'ajout : les lignes existantes doivent recevoir une
    # valeur, sinon la colonne NOT NULL échoue sur une table non vide.
    op.add_column(
        "profiles",
        sa.Column(
            "parse_etat",
            sa.String(16),
            nullable=False,
            server_default="en_attente",
        ),
    )
    op.add_column("profiles", sa.Column("parse_erreur", sa.String(64), nullable=True))
    op.add_column(
        "profiles",
        sa.Column("parse_demarre_le", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_check_constraint(
        "ck_profiles_parse_etat",
        "profiles",
        "parse_etat IN ('en_attente', 'en_cours', 'pret', 'echec')",
    )
    op.drop_column("profiles", "cv_file_path")


def downgrade() -> None:
    op.add_column("profiles", sa.Column("cv_file_path", sa.String(512), nullable=True))
    op.drop_constraint("ck_profiles_parse_etat", "profiles", type_="check")
    op.drop_column("profiles", "parse_demarre_le")
    op.drop_column("profiles", "parse_erreur")
    op.drop_column("profiles", "parse_etat")
