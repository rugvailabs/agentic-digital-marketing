"""trend_sources per-platform rows

Revision ID: 488f6ad23a2b
Revises: 12dba3e1fb88
Create Date: 2026-10-27 19:01:09.203740

Hand-corrected in two places that autogenerate gets wrong for a native enum.

First, `reddit` and `instagram` are new members of `source_name`, and
autogenerate does not notice enum changes at all: it listed the six values
inside create_table and emitted no ALTER TYPE, so the two new ones would
never have existed in the database. Postgres needs them added explicitly.

Second, the generated create_table would have tried to CREATE TYPE
source_name, which already exists from the first migration and fails. The
column below uses create_type=False so the table reuses the type it is
extending.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "488f6ad23a2b"
down_revision: str | None = "12dba3e1fb88"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: Platforms added to `source_name` by this revision.
NEW_PLATFORMS = ("reddit", "instagram")

#: Every member after this revision, for the column definition.
SOURCE_NAMES = ("google_trends", "google_news", "youtube", "x", *NEW_PLATFORMS)


def upgrade() -> None:
    # ALTER TYPE ... ADD VALUE is transactional on Postgres 12+, but a value
    # added in a transaction cannot be *used* in that same transaction. The
    # table below only references the type, never writes one of the new
    # values, so this is safe where an INSERT would not be.
    for platform in NEW_PLATFORMS:
        op.execute(f"ALTER TYPE source_name ADD VALUE IF NOT EXISTS '{platform}'")

    op.create_table(
        "trend_sources",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("trend_id", sa.Integer(), nullable=False),
        sa.Column(
            "platform",
            # create_type=False: the type exists already and this revision
            # has just extended it.
            postgresql.ENUM(*SOURCE_NAMES, name="source_name", create_type=False),
            nullable=False,
        ),
        sa.Column("rank", sa.Integer(), nullable=True),
        sa.Column("volume", sa.Integer(), nullable=False),
        sa.Column("hashtags", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("url", sa.Text(), nullable=True),
        sa.Column("seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["trend_id"],
            ["trends.id"],
            name=op.f("fk_trend_sources_trend_id_trends"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_trend_sources")),
        sa.UniqueConstraint("trend_id", "platform", name="uq_trend_sources_trend_platform"),
    )
    op.create_index(
        "ix_trend_sources_platform_rank", "trend_sources", ["platform", "rank"], unique=False
    )
    op.create_index("ix_trend_sources_trend_id", "trend_sources", ["trend_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_trend_sources_trend_id", table_name="trend_sources")
    op.drop_index("ix_trend_sources_platform_rank", table_name="trend_sources")
    op.drop_table("trend_sources")

    # `reddit` and `instagram` stay in source_name. Postgres has no DROP
    # VALUE, and the alternative — rebuild the type, rewrite every column
    # using it — would risk trend_snapshots and trends to undo two unused
    # labels. Downgrading leaves them orphaned in the type, which is
    # harmless: nothing reads a member it never writes.
