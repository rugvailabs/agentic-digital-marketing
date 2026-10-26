"""job kind and video assets

Revision ID: 12dba3e1fb88
Revises: 2aef613ed3f3
Create Date: 2026-10-26
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "12dba3e1fb88"
down_revision: str | None = "2aef613ed3f3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: New members of existing native enums. Postgres 16 allows ADD VALUE inside a
#: transaction as long as nothing in the same transaction uses the new value,
#: which nothing here does.
JOB_STATUS_ADDITIONS = ("voicing",)
ASSET_KIND_ADDITIONS = ("video", "audio", "script")


def upgrade() -> None:
    for value in JOB_STATUS_ADDITIONS:
        op.execute(f"ALTER TYPE job_status ADD VALUE IF NOT EXISTS '{value}'")
    for value in ASSET_KIND_ADDITIONS:
        op.execute(f"ALTER TYPE asset_kind ADD VALUE IF NOT EXISTS '{value}'")

    job_kind = sa.Enum("post", "reel", name="job_kind")
    job_kind.create(op.get_bind(), checkfirst=True)
    # server_default so the existing rows — all of them posts — become valid
    # without a data migration.
    op.add_column(
        "content_jobs",
        sa.Column("kind", job_kind, nullable=False, server_default="post"),
    )

    # The Desk asks for "the latest post" and "the latest reel" separately, so
    # the index that served trend_id alone is now the wrong shape.
    op.drop_index("ix_content_jobs_trend_id", table_name="content_jobs")
    op.create_index(
        "ix_content_jobs_trend_kind", "content_jobs", ["trend_id", "kind"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_content_jobs_trend_kind", table_name="content_jobs")
    op.create_index("ix_content_jobs_trend_id", "content_jobs", ["trend_id"], unique=False)
    op.drop_column("content_jobs", "kind")
    sa.Enum(name="job_kind").drop(op.get_bind(), checkfirst=True)
    # The added enum members stay: Postgres cannot drop a value from an enum,
    # and recreating job_status/asset_kind would mean rewriting every row that
    # references them. Harmless — nothing reads a value the code does not know.
