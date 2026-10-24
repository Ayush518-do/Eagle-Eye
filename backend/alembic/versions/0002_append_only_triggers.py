"""database triggers: findings and review_events are append-only

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-24

The ORM guards in app/models.py stop the application from changing history. These triggers
stop everything else too (raw SQL, Core statements, other tools using the same file).

SQLite drops a table's triggers when the table is dropped or rebuilt. Alembic's batch mode
rebuilds a table to change a column, so any future migration that alters `findings` or
`review_events` must recreate these triggers (see tests/test_db_triggers.py).
DROP TABLE cannot be blocked by a trigger in SQLite.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

PROTECTED = {"findings": "findings are immutable", "review_events": "review_events is append-only"}
ACTIONS = ("UPDATE", "DELETE")


def upgrade() -> None:
    if op.get_bind().dialect.name != "sqlite":
        # Do not silently skip: the guarantee would be missing without anyone noticing.
        raise NotImplementedError("These triggers are written for SQLite only.")
    for table, message in PROTECTED.items():
        for action in ACTIONS:
            op.execute(
                f"CREATE TRIGGER {table}_no_{action.lower()} BEFORE {action} ON {table} "
                f"BEGIN SELECT RAISE(ABORT, '{message}: {action} is not allowed'); END"
            )


def downgrade() -> None:
    if op.get_bind().dialect.name != "sqlite":
        return
    for table in PROTECTED:
        for action in ACTIONS:
            op.execute(f"DROP TRIGGER IF EXISTS {table}_no_{action.lower()}")
