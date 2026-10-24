"""image_alignments

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-24

Per-image 4-point homography between the drawing and the photo (Contract E, ghost overlay).
A plain CREATE TABLE: no existing table is touched, so no triggers are affected.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "image_alignments",
        sa.Column("image_id", sa.String(length=40), primary_key=True),
        sa.Column("drawing_page", sa.Integer(), nullable=False),
        sa.Column("drawing_points", sa.JSON(), nullable=False),
        sa.Column("photo_points", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["image_id"], ["images.id"]),
    )


def downgrade() -> None:
    op.drop_table("image_alignments")
