"""curator v3 fields

Two nullable columns, and nullable on purpose. A row that has never been
curated has no answer to either question, which is a different thing from
scoring zero relevance or having no reason to be trending. The curator fills
them; the non-LLM merge leaves them null, and the UI reads null as "not
curated yet" rather than as a bad score.

No backfill: inventing a relevance for rows the curator has not seen would
put a number on the board that nothing produced.

Revision ID: e6fa76edbd41
Revises: 488f6ad23a2b
Create Date: 2026-10-27 22:10:08.840023
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "e6fa76edbd41"
down_revision: str | None = "488f6ad23a2b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("trends", sa.Column("why_trending", sa.Text(), nullable=True))
    op.add_column("trends", sa.Column("relevance_to_region", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("trends", "relevance_to_region")
    op.drop_column("trends", "why_trending")
