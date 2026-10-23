"""regions, trend_snapshots, trends

Revision ID: b9e3c7efe9de
Revises:
Create Date: 2026-10-23 11:30:09.554303
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "b9e3c7efe9de"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # pgvector is part of the stack per CLAUDE.md. Nothing embeds yet, but
    # creating the extension here means step 2's embedding columns are a plain
    # column migration rather than a privileged DDL step.
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "regions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(length=16), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column(
            "kind",
            sa.Enum("country", "state", "union_territory", "city", name="region_kind"),
            nullable=False,
        ),
        sa.Column("parent_id", sa.Integer(), nullable=True),
        sa.Column("google_trends_geo", sa.String(length=16), nullable=True),
        sa.Column("x_woeid", sa.Integer(), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
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
            ["parent_id"],
            ["regions.id"],
            name=op.f("fk_regions_parent_id_regions"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_regions")),
        sa.UniqueConstraint("code", name=op.f("uq_regions_code")),
    )
    op.create_index("ix_regions_kind_sort_order", "regions", ["kind", "sort_order"], unique=False)
    op.create_index("ix_regions_parent_id", "regions", ["parent_id"], unique=False)
    op.create_table(
        "trend_snapshots",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("region_id", sa.Integer(), nullable=False),
        sa.Column(
            "source",
            sa.Enum("google_trends", "google_news", "youtube", "x", name="source_name"),
            nullable=False,
        ),
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "status",
            sa.Enum("ok", "empty", "skipped", "error", name="snapshot_status"),
            nullable=False,
        ),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("item_count", sa.Integer(), nullable=False),
        sa.Column("items", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
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
            ["region_id"],
            ["regions.id"],
            name=op.f("fk_trend_snapshots_region_id_regions"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_trend_snapshots")),
        sa.UniqueConstraint("region_id", "source", "run_id", name="uq_trend_snapshots_run"),
    )
    op.create_index(
        "ix_trend_snapshots_captured_at", "trend_snapshots", ["captured_at"], unique=False
    )
    op.create_index(
        "ix_trend_snapshots_region_captured",
        "trend_snapshots",
        ["region_id", "captured_at"],
        unique=False,
    )
    op.create_table(
        "trends",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("region_id", sa.Integer(), nullable=False),
        sa.Column("topic", sa.String(length=300), nullable=False),
        sa.Column("topic_key", sa.String(length=300), nullable=False),
        sa.Column("category", sa.String(length=64), nullable=True),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("volume", sa.Integer(), nullable=False),
        sa.Column("velocity", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("hashtags", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("sources", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("evidence", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "ingested",
                "curated",
                "planned",
                "written",
                "image_rendered",
                "video_rendered",
                "reviewed",
                "published",
                "skipped",
                name="pipeline_status",
            ),
            nullable=False,
        ),
        sa.Column("safety_flag", sa.String(length=64), nullable=True),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
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
            ["region_id"],
            ["regions.id"],
            name=op.f("fk_trends_region_id_regions"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_trends")),
        sa.UniqueConstraint("region_id", "topic_key", name="uq_trends_region_id_topic_key"),
    )
    op.create_index("ix_trends_last_seen_at", "trends", ["last_seen_at"], unique=False)
    op.create_index("ix_trends_region_rank", "trends", ["region_id", "rank"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_trends_region_rank", table_name="trends")
    op.drop_index("ix_trends_last_seen_at", table_name="trends")
    op.drop_table("trends")
    op.drop_index("ix_trend_snapshots_region_captured", table_name="trend_snapshots")
    op.drop_index("ix_trend_snapshots_captured_at", table_name="trend_snapshots")
    op.drop_table("trend_snapshots")
    op.drop_index("ix_regions_parent_id", table_name="regions")
    op.drop_index("ix_regions_kind_sort_order", table_name="regions")
    op.drop_table("regions")

    # create_table creates native enum types implicitly but autogenerate never
    # drops them; without this a downgrade/upgrade cycle fails on "type exists".
    for enum_name in ("pipeline_status", "snapshot_status", "source_name", "region_kind"):
        sa.Enum(name=enum_name).drop(op.get_bind(), checkfirst=True)

    # The extension is left in place: other schemas in the same database may
    # depend on it, and dropping it is not this migration's business.
