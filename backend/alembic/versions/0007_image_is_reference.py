"""images.is_reference

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-25

Boolean flag identifying the approved reference / baseline photo for each cabinet.
Nullable=False with a 0 default so existing rows backfill to "not a reference". The
services layer enforces at-most-one-true per cabinet; no DB-side partial unique
index is used (SQLite's support for `WHERE` partial indexes is uneven across
versions).

A plain ADD COLUMN: no table rebuild, so no triggers are affected.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: Union[str, None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("images") as batch_op:
        batch_op.add_column(sa.Column("is_reference", sa.Boolean(), nullable=False, server_default=sa.text("0")))
        batch_op.create_index("ix_images_is_reference", ["is_reference"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("images") as batch_op:
        batch_op.drop_index("ix_images_is_reference")
        batch_op.drop_column("is_reference")
