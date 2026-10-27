"""workspaces, brand profile, editorial status

Hand-corrected for the rows already in the table. Autogenerate adds
workspace_id, products and do_not_mention as NOT NULL with no default, which
is only valid on an empty table — there is one brand and 35 jobs here, and
every one of those statements would fail.

So each goes on nullable, gets backfilled to the default workspace, and is
constrained afterwards. The same shape any of these would need in
production, where "the table is empty" is never the situation.

The brand slug also stops being globally unique and becomes unique per
workspace, because two teams may each have a brand called "acme" and the
slug is how a URL names one.

Revision ID: 55b65c250dca
Revises: e6fa76edbd41
Create Date: 2026-10-28 04:08:50.402561
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "55b65c250dca"
down_revision: str | None = "e6fa76edbd41"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "workspaces",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("slug", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
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
        sa.PrimaryKeyConstraint("id", name=op.f("pk_workspaces")),
        sa.UniqueConstraint("slug", name=op.f("uq_workspaces_slug")),
    )

    # The one workspace everything belongs to until auth exists. Its id is
    # pinned to 1 and the sequence advanced past it, so a later insert
    # cannot collide with the row every existing brand is about to point at.
    op.execute(
        "INSERT INTO workspaces (id, slug, name) VALUES (1, 'default', 'Default workspace')"
    )
    op.execute("SELECT setval('workspaces_id_seq', (SELECT max(id) FROM workspaces))")

    # ── brands ────────────────────────────────────────────────────────────
    op.add_column("brands", sa.Column("workspace_id", sa.Integer(), nullable=True))
    op.add_column(
        "brands",
        sa.Column("products", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column("brands", sa.Column("default_region_code", sa.String(length=16), nullable=True))
    op.add_column(
        "brands",
        sa.Column("do_not_mention", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.execute(
        "UPDATE brands SET workspace_id = 1, "
        "products = COALESCE(products, '[]'::jsonb), "
        "do_not_mention = COALESCE(do_not_mention, '[]'::jsonb)"
    )
    op.alter_column("brands", "workspace_id", nullable=False)
    op.alter_column("brands", "products", nullable=False, server_default=sa.text("'[]'::jsonb"))
    op.alter_column(
        "brands", "do_not_mention", nullable=False, server_default=sa.text("'[]'::jsonb")
    )

    op.drop_constraint(op.f("uq_brands_slug"), "brands", type_="unique")
    op.create_unique_constraint("uq_brands_workspace_slug", "brands", ["workspace_id", "slug"])
    op.create_index("ix_brands_workspace_id", "brands", ["workspace_id"], unique=False)
    op.create_foreign_key(
        op.f("fk_brands_workspace_id_workspaces"),
        "brands",
        "workspaces",
        ["workspace_id"],
        ["id"],
        ondelete="CASCADE",
    )

    # ── content_jobs ──────────────────────────────────────────────────────
    op.add_column("content_jobs", sa.Column("workspace_id", sa.Integer(), nullable=True))
    # Through the brand rather than a flat 1: it is the same answer today and
    # the correct one once a second workspace exists, and a job belonging to
    # a different workspace than its brand would be a bug nobody could see.
    op.execute(
        "UPDATE content_jobs SET workspace_id = brands.workspace_id "
        "FROM brands WHERE brands.id = content_jobs.brand_id"
    )
    op.execute("UPDATE content_jobs SET workspace_id = 1 WHERE workspace_id IS NULL")
    op.alter_column("content_jobs", "workspace_id", nullable=False)

    # Created explicitly. A sa.Enum inside add_column does not emit CREATE
    # TYPE on this driver, so the ALTER TABLE arrives first and fails with
    # 'type "editorial_status" does not exist' — the same trap as source_name
    # in the trend_sources migration.
    editorial = postgresql.ENUM(
        "draft", "approved", "scheduled", "posted", name="editorial_status"
    )
    editorial.create(op.get_bind(), checkfirst=True)
    op.add_column(
        "content_jobs",
        sa.Column(
            "editorial_status",
            postgresql.ENUM(
                "draft",
                "approved",
                "scheduled",
                "posted",
                name="editorial_status",
                create_type=False,
            ),
            server_default="draft",
            nullable=False,
        ),
    )
    op.add_column(
        "content_jobs", sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=True)
    )

    op.create_index("ix_content_jobs_scheduled_at", "content_jobs", ["scheduled_at"], unique=False)
    op.create_index(
        "ix_content_jobs_workspace_created",
        "content_jobs",
        ["workspace_id", "created_at"],
        unique=False,
    )
    op.create_foreign_key(
        op.f("fk_content_jobs_workspace_id_workspaces"),
        "content_jobs",
        "workspaces",
        ["workspace_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("fk_content_jobs_workspace_id_workspaces"), "content_jobs", type_="foreignkey"
    )
    op.drop_index("ix_content_jobs_workspace_created", table_name="content_jobs")
    op.drop_index("ix_content_jobs_scheduled_at", table_name="content_jobs")
    op.drop_column("content_jobs", "scheduled_at")
    op.drop_column("content_jobs", "editorial_status")
    op.drop_column("content_jobs", "workspace_id")
    # The enum type outlives its column on Postgres and would block a second
    # upgrade with "type already exists".
    op.execute("DROP TYPE IF EXISTS editorial_status")

    op.drop_constraint(op.f("fk_brands_workspace_id_workspaces"), "brands", type_="foreignkey")
    op.drop_index("ix_brands_workspace_id", table_name="brands")
    op.drop_constraint("uq_brands_workspace_slug", "brands", type_="unique")
    op.create_unique_constraint(op.f("uq_brands_slug"), "brands", ["slug"])
    op.drop_column("brands", "do_not_mention")
    op.drop_column("brands", "default_region_code")
    op.drop_column("brands", "products")
    op.drop_column("brands", "workspace_id")
    op.drop_table("workspaces")
