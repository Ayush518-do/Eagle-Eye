"""expected_items.layout

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-24

Contract A `layout` on expected items. Nullable: hand-typed items and older parsers may not
include it. Used by the ghost overlay (Contract E) to project the expected box onto the photo.

A plain ADD COLUMN: no table rebuild, so no triggers are affected.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("expected_items") as batch_op:
        batch_op.add_column(sa.Column("layout", sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("expected_items") as batch_op:
        batch_op.drop_column("layout")
