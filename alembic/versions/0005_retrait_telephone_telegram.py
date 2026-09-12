"""retrait du téléphone et de telegram_id

Décision du porteur du projet le 2026-09-12 : Telegram cesse d'être un client
du produit, et le numéro de téléphone quitte la table d'identité.

`phone` était UNIQUE : tant que la colonne existait avec cette contrainte, un
tiers pouvait réserver le numéro d'autrui sur son propre compte et l'empêcher
de le saisir sur le sien. La rendre facultative (migration 0004) avait réduit
le trou sans le fermer. Le supprimer le ferme.

`telegram_id` part avec le client Telegram : plus de bot, plus d'identifiant
Telegram à rattacher.

L'identité d'un compte est désormais son adresse email, et rien d'autre. Le
numéro réapparaîtra en Phase 3 dans `profiles.structured`, extrait du CV, sans
contrainte d'unicité ni prétention de vérification.

PostgreSQL supprime avec une colonne les index qui la portent : il n'y a pas
d'index à défaire séparément.

Le `downgrade` recrée les deux colonnes nullables avec leurs index uniques,
mais **ne restaure aucune donnée** : il rend le schéma, pas le contenu. C'est
acceptable ici, la base ne portait aucun utilisateur au moment du retrait.

Noms d'index relevés en base avant écriture (`\\d users`, 2026-09-12) :
`ix_users_phone` et `ix_users_telegram_id` — repris tels quels ci-dessous.

Revision ID: a1c2e3f40005
Revises: a1c2e3f40004
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "a1c2e3f40005"
down_revision: str | None = "a1c2e3f40004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_column("users", "phone")
    op.drop_column("users", "telegram_id")


def downgrade() -> None:
    op.add_column("users", sa.Column("phone", sa.String(length=32), nullable=True))
    op.add_column("users", sa.Column("telegram_id", sa.BigInteger(), nullable=True))
    op.create_index(op.f("ix_users_phone"), "users", ["phone"], unique=True)
    op.create_index(op.f("ix_users_telegram_id"), "users", ["telegram_id"], unique=True)
