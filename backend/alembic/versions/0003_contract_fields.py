"""Contract A rating metadata and Contract B observation_id

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-24

- expected_items: rating_source, rating_page, source_page (all nullable, Contract A).
- observations: observation_id (Contract B), unique per image. Existing rows, if any, are
  backfilled from the server id so the NOT NULL constraint can be applied without losing rows.

Only `expected_items` (plain ADD COLUMN) and `observations` (rebuilt for the new constraint)
are touched. `findings` and `review_events` are not rebuilt, so their append-only triggers
from 0002 are untouched; tests/test_db_triggers.py checks that at head.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("expected_items") as batch_op:
        batch_op.add_column(sa.Column("rating_source", sa.String(length=50), nullable=True))
        batch_op.add_column(sa.Column("rating_page", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("source_page", sa.Integer(), nullable=True))

    with op.batch_alter_table("observations") as batch_op:
        batch_op.add_column(sa.Column("observation_id", sa.String(length=100), nullable=True))
    op.execute("UPDATE observations SET observation_id = id WHERE observation_id IS NULL")
    with op.batch_alter_table("observations") as batch_op:
        batch_op.alter_column("observation_id", existing_type=sa.String(length=100), nullable=False)
        batch_op.create_unique_constraint(
            "uq_observations_image_observation", ["image_id", "observation_id"]
        )


def downgrade() -> None:
    # Dropping these columns discards the stored Contract A/B values.
    with op.batch_alter_table("observations") as batch_op:
        batch_op.drop_constraint("uq_observations_image_observation", type_="unique")
        batch_op.drop_column("observation_id")
    with op.batch_alter_table("expected_items") as batch_op:
        batch_op.drop_column("source_page")
        batch_op.drop_column("rating_page")
        batch_op.drop_column("rating_source")
