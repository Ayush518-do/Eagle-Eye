"""Alembic environment. The URL is taken from the `sqlalchemy.url` option if a caller set one
(tests do), otherwise from the app settings (DATABASE_URL).

Works from the repository root and from `backend/`: the repo root is put on `sys.path` here
instead of relying on the caller's working directory.

SQLite and foreign keys: a batch migration rebuilds a table by dropping and recreating it, which
fails on a parent table while foreign keys are enforced. So migrations run with enforcement off
(SQLite's documented procedure) and `PRAGMA foreign_key_check` runs afterwards; any violation
fails the migration loudly. Enforcement is switched off only on the migration's own connection;
the application's connections (`make_engine()` default) keep it on.
"""
import sys
from pathlib import Path

from alembic import context

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.app.config import get_settings  # noqa: E402
from backend.app.db import make_engine  # noqa: E402
from backend.app.models import Base  # noqa: E402

config = context.config
target_metadata = Base.metadata


def _url() -> str:
    return config.get_main_option("sqlalchemy.url") or get_settings().database_url


def run_migrations_offline() -> None:
    context.configure(
        url=_url(), target_metadata=target_metadata, literal_binds=True, render_as_batch=True
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = make_engine(_url(), foreign_keys=False)
    with engine.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,  # SQLite cannot ALTER most things in place
        )
        with context.begin_transaction():
            context.run_migrations()
        if connection.dialect.name == "sqlite":
            violations = connection.exec_driver_sql("PRAGMA foreign_key_check").fetchall()
            if violations:
                raise RuntimeError(
                    "Foreign key check failed after migration "
                    "(table, rowid, parent table, fk index): "
                    + "; ".join(str(tuple(v)) for v in violations[:10])
                )
    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
