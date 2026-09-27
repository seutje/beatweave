"""Track when a recent project was last opened."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("projects", sa.Column("last_opened_at", sa.DateTime(timezone=True)))
    op.execute("UPDATE projects SET last_opened_at = updated_at WHERE last_opened_at IS NULL")
    with op.batch_alter_table("projects") as batch:
        batch.alter_column("last_opened_at", nullable=False)


def downgrade() -> None:
    with op.batch_alter_table("projects") as batch:
        batch.drop_column("last_opened_at")
