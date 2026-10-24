"""design_revisions.parser_version

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-24

Contract A `parser_version`, stored on the design revision. Nullable: expected items typed by
hand have no parser. `drawing_file_sha256` needs no column; it is checked against the existing
`design_revisions.drawing_sha256`.

A plain ADD COLUMN: no table rebuild, so no triggers are affected.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("design_revisions") as batch_op:
        batch_op.add_column(sa.Column("parser_version", sa.String(length=100), nullable=True))


def downgrade() -> None:
    # Discards the stored parser versions.
    with op.batch_alter_table("design_revisions") as batch_op:
        batch_op.drop_column("parser_version")
