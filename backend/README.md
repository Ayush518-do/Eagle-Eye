# Backend (Part 3)

FastAPI service. Task list: [`../docs/team/backend.md`](../docs/team/backend.md).

```text
backend/
├── app/
│   ├── main.py              # app, CORS, /health
│   ├── config.py            # settings from environment / .env
│   ├── db.py                # SQLAlchemy engine and session dependency
│   ├── ids.py               # server-generated public ids (INS-, IMG-, F-, OBS-, DREV-, ITEM-)
│   ├── models.py            # the eight tables from the task file + append-only guards
│   ├── schemas.py           # contracts A, B, C (docs/contracts.md)
│   ├── api/routes.py        # /api/health, /api/model/status, POST /api/uploads
│   ├── services/storage.py  # upload checks: real file type, size, safe names, SHA-256
│   └── pipeline/compare.py  # starter tag-based comparison (engine team's folder)
├── alembic.ini, alembic/    # database migrations (0001 tables, 0002 triggers, 0003 contract fields, 0004 parser_version)
├── tests/                   # pytest
├── requirements.txt
└── requirements-dev.txt     # + pytest, httpx
```

## Setup and run (from the repository root)

```bash
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r backend/requirements-dev.txt
cp .env.example .env                                   # optional; defaults work without it
alembic -c backend/alembic.ini upgrade head            # creates the database
uvicorn backend.app.main:app --reload                  # http://127.0.0.1:8000/docs
pytest backend/tests -q
```

Migrations also work from inside `backend/`: `cd backend && alembic upgrade head`.
Other useful commands: `alembic -c backend/alembic.ini current`, `... check` (fails if
`models.py` and the migrations disagree), `... downgrade -1`.

## Configuration

Settings come from environment variables or the `.env` file in the repository root
(see `../.env.example`). Environment variables win over `.env`.

| Setting | Default | Notes |
|---|---|---|
| `DATABASE_URL` | `sqlite:///<repo>/backend/eagle_eye.db` | A relative SQLite path is read relative to the **repository root**. |
| `UPLOAD_DIR` | `<repo>/backend/uploads` | A relative path is read relative to the **repository root**. |
| `MAX_UPLOAD_MB` | `20` | |

Defaults do not depend on the directory you start the process in. Both defaults are ignored by
Git (`backend/uploads/`, `*.db`). Note that `.env.example` sets `UPLOAD_DIR=./uploads`, which
points at `<repo>/uploads`; that folder is not currently in `.gitignore`, so either remove the
line from your `.env` or keep uploads out of `git add`.

## Database

Eight tables, as listed in the task file: `cabinets`, `design_revisions`, `expected_items`,
`inspections`, `images`, `observations`, `findings`, `review_events`.

- **Append-only history.** `findings` and `review_events` cannot be updated or deleted: the ORM
  refuses it, and SQLite triggers (migration 0002) refuse it for raw SQL too. A finding's current
  status is derived from its original status plus the latest review event.
- **Migrations rebuild tables in SQLite**, and a rebuild drops that table's triggers. A migration
  that alters `findings` or `review_events` must recreate the triggers;
  `tests/test_db_trigger_integrity.py` fails if any trigger is missing at the latest revision.
- **Foreign keys.** The app enforces them on every connection. Migrations switch enforcement off on
  their own connection (needed for table rebuilds) and run `PRAGMA foreign_key_check` afterwards;
  a violation fails the migration.
- **Contract fields kept:** `expected_items.rating_source`, `rating_page`, `source_page` (Contract A)
  and `observations.observation_id` (Contract B, unique per image; the server key `id` is separate).
- **Contract A envelope:** `drawing_file_sha256` is the PDF hash already stored as
  `design_revisions.drawing_sha256` (no second column); when supplied it must match, otherwise
  409. `design_revisions.parser_version` is nullable and is kept when a manual list omits it.
  `services/expected_items.py` replaces a revision's expected items atomically (replace, never
  append); `POST /api/design-revisions/{id}/expected-items` calls it.

## What works now
- `GET /health`, `GET /api/health`
- `GET /api/model/status` — says which models are configured; does not load them
- `POST /api/uploads` — JPEG/PNG/PDF only (type decided from the first bytes; the content is not
  decoded or parsed), size limit, generated file names. The inspection and drawing endpoints below
  validate more strictly.
- `compare()` — matches expected tags to OCR-read tags; unread tags are `inconclusive`, not missing
- Database models, migrations and a session dependency
- All 13 endpoints of `docs/team/backend.md` Step 2, plus `GET` for expected items and observations.
  Runs use `BackgroundTasks` and the starter `compare()`. A reinspection is a new linked inspection
  that is run like any other; it never marks earlier findings resolved by itself.
  Request and response shapes are in `docs/contracts.md` section D (proposals until agreed).
- Drawings: a complete PDF is required (header, trailer and a valid cross-reference pointer).
- Photos: JPEG/PNG, 1-10 per inspection, at most about 89 million pixels (Pillow's own
  decompression-bomb threshold; checked from the header before anything is decoded).
  PNG files are checked completely (chunk checksums and the pixel stream). JPEG files are walked
  marker by marker (frame header, every scan, no invalid marker inside the data, end marker) and
  then fully decoded with Pillow (`Image.load()`); the decoded format and size must match.
  Decoding shows the file is a complete, decodable image. It does not show the photo is sharp or
  shows a real cabinet. Image quality is not measured and is reported as the flag
  `quality_not_measured`.
- Pillow (`pillow>=10,<12`, the same range `ml/` uses) is a declared backend dependency.
- Every error body is `{"detail": "plain message"}`, including request-validation errors.

## Known gaps and proposals (need a decision)

- **Damage inside a complete JPEG scan cannot be detected.** The JPEG decoder (libjpeg) hides
  errors inside the pixel data: zeroed, garbage or bit-flipped data still decodes, to a distorted
  picture, and a file cut short and then given a fresh end marker decodes with a grey remainder.
  A JPEG has no checksum, so no decoder can tell. Truncation, missing or invalid markers, missing
  tables, wrong dimensions and non-JPEG data are rejected. A photo's sha256 is stored, which
  detects later changes but not damage that was already present.
- **PDF content is not parsed.** Drawings get a structural check only (header, trailer, a valid
  cross-reference pointer). Parsing the pages needs a PDF library (for example `pypdf`), which is
  not declared; adding one is a separate decision.
- **Revision labels are not unique per cabinet.** No document requires it, and Contract C now
  returns the label as `design_revision_id`, so two `REV-A` revisions would be ambiguous there.
  Proposal: a unique index on (cabinet, lower-cased label) with a 409 on duplicates; add it only
  after the team agrees, because existing data could already contain duplicates.
- **An inspection can stay `running` if the server stops mid-run.** It cannot be restarted (409).
  Resetting every `running` row at startup is unsafe when more than one server process shares the
  database. Proposal: a migration adding `inspections.run_started_at` and `run_token`; the job
  finishes with `UPDATE ... WHERE state='running' AND run_token=:token` (and rolls back its findings
  if no row matched); a `RUN_TIMEOUT_SECONDS` setting lets `GET` and `POST /run` mark a `running`
  inspection older than the timeout as `failed` ("interrupted") with the same conditional update.

## Next (see task list)
The engine's `run_inspection` (rating findings, comparison with the previous inspection, the rule
for `resolved_after_reinspection`), image-quality checks, and the decisions listed above.
