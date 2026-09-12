"""téléphone facultatif à l'inscription

Décision du porteur du projet le 2026-09-12, après la revue finale de la
Phase 2 : `users.phone` cesse d'être demandé à l'inscription.

Le défaut fermé : le code à 6 chiffres ne prouve la possession que de
l'adresse email, jamais celle du numéro. Un attaquant pouvait donc
s'inscrire avec sa propre adresse et le numéro d'une victime — qui se
retrouvait alors dans l'incapacité de créer son propre compte
(`TelephoneDejaUtilise`), et dont le futur contact Telegram partagé se
serait rattaché au compte de l'attaquant plutôt qu'au sien
(`lier_telegram` retrouvait jusqu'ici un compte par numéro).

On ne collecte désormais le numéro que là où il est vérifié gratuitement :
la liaison Telegram (Telegram le certifie via « partager mon contact »), et
plus tard le webhook mobile money (Phase 6).

`phone` passe donc en NULLABLE, sans toucher à son index unique : en
PostgreSQL un index unique tolère plusieurs NULL, exactement comme
`telegram_id` depuis la migration 0002.

Le `downgrade` ne fonctionne que si aucune ligne n'a `phone IS NULL` au
moment de son exécution — sinon `NOT NULL` échoue, bruyamment, plutôt que
d'inventer un numéro pour les lignes qui n'en ont pas. C'est voulu (même
logique que la migration 0002 pour `email`/`phone`).

Revision ID: a1c2e3f40004
Revises: a1c2e3f40003
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "a1c2e3f40004"
down_revision: str | None = "a1c2e3f40003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column("users", "phone", existing_type=sa.String(length=32), nullable=True)


def downgrade() -> None:
    op.alter_column("users", "phone", existing_type=sa.String(length=32), nullable=False)
