"""trend member keys

Revision ID: 2aef613ed3f3
Revises: dc1a3d967176
Create Date: 2026-10-23 23:09:20.530991
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "2aef613ed3f3"
down_revision: str | None = "dc1a3d967176"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # server_default, not just nullable=False: the table already holds rows,
    # and NOT NULL with no default cannot be added to a populated table.
    # Existing topics start empty and are seeded from their own `evidence` on
    # the next curate, so no data migration is needed here.
    op.add_column(
        "trends",
        sa.Column(
            "member_keys",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )


def downgrade() -> None:
    op.drop_column("trends", "member_keys")
