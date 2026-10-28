"""brand logo key

The storage key beside the public URL, because the two have different
readers. `logo_url` is built from S3_PUBLIC_URL — localhost on a published
port locally — which a browser can fetch and a container cannot. The Pillow
templates and the Remotion renderer both run in containers.

Nullable with no backfill: the one brand that exists has no logo, and a key
cannot be recovered from a URL without assuming the prefix that made it.
A logo uploaded from here on sets both.

Revision ID: ae73bd26c5bd
Revises: 55b65c250dca
Create Date: 2026-10-28 04:59:59.682512
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "ae73bd26c5bd"
down_revision: str | None = "55b65c250dca"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("brands", sa.Column("logo_key", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("brands", "logo_key")
