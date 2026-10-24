# Task 1: Backend (API and database)

**Branch:** `feature/backend-pipeline` · **You own:** `backend/app/` except `backend/app/pipeline/`,
plus `backend/alembic/` and `backend/tests/` (except `test_engine_*.py`).
**Do not edit:** `backend/app/pipeline/` (Task 3), `frontend/` (Task 2), `ml/`.

## What you are building

The backend is the middle of the system. It:

1. receives files from the frontend (drawing PDF, cabinet photos),
2. stores records in a database (cabinets, inspections, findings, review decisions),
3. calls the inspection engine (Task 3) to produce findings,
4. returns results to the frontend in the agreed format (contract C in `docs/contracts.md`).

```text
Frontend ──HTTP──► Backend API ──► database (SQLite file)
                       │
                       └──► inspection engine: run_inspection(...)  → findings
                       └──► ml/interfaces.py (later)                → observations
```

## What already works (do not rebuild)

| File | What it does |
|---|---|
| `app/main.py` | Creates the app and allows the frontend to call it (CORS) |
| `app/config.py` | Reads settings from `.env` |
| `app/schemas.py` | Data shapes for contracts A, B and C. Use these; don't invent new shapes |
| `app/api/routes.py` | `GET /api/health`, `GET /api/model/status`, `POST /api/uploads` |
| `app/services/storage.py` | Saves uploads safely: checks the real file type and size, and generates file names |
| `tests/` | 13 tests; run `pytest backend/tests -q` |

Start by running it ([`../setup.md`](../setup.md)), opening http://127.0.0.1:8000/docs and trying
`POST /api/uploads` with a photo.

## Step 1: Database

Use **SQLAlchemy 2** (lets you work with Python classes instead of SQL) and **Alembic** (keeps
a numbered history of table changes, called *migrations*, so everyone's database matches).

```bash
pip install "sqlalchemy>=2,<3" "alembic>=1.13,<2"     # add both to backend/requirements.txt
alembic init backend/alembic
```

Create `backend/app/db.py` (engine + session) and `backend/app/models.py` with these tables:

| Table | Columns |
|---|---|
| `cabinets` | `id` (text, e.g. `CAB-001`), `name`, `created_at` |
| `design_revisions` | `id`, `cabinet_id`, `label` (e.g. `REV-A`), `drawing_file_id`, `drawing_sha256`, `created_at` |
| `expected_items` | `id`, `design_revision_id`, `tag`, `part_number`, `description`, `quantity`, `rating_value`, `rating_needs_review` |
| `inspections` | `id`, `cabinet_id`, `design_revision_id`, `state` (`queued`/`running`/`done`/`failed`), `error`, `overall_status`, `previous_inspection_id`, `created_at` |
| `images` | `id`, `inspection_id`, `file_id`, `sha256`, `width`, `height`, `quality_flags` (JSON) |
| `observations` | `id`, `image_id`, `source`, `kind`, `class_name`, `bbox` (JSON), `confidence`, `text`, `raw_text`, `text_confidence`, `model` (JSON) |
| `findings` | `id`, `inspection_id`, `type`, `tag`, `expected_value`, `observed_text`, `detector_confidence`, `ocr_confidence`, `status`, `reason`, `evidence` (JSON) |
| `review_events` | `id`, `finding_id`, `decision`, `reviewer`, `note`, `created_at` |

**Rule:** never update or delete a `review_events` row. A finding's current status is its
original status plus the latest review event. This keeps the full history (the "quality passport").

Example model:

```python
# backend/app/models.py
from datetime import datetime, timezone
from sqlalchemy import ForeignKey, JSON, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

class Base(DeclarativeBase):
    pass

class Cabinet(Base):
    __tablename__ = "cabinets"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc))
```

Then run `alembic revision --autogenerate -m "initial tables"` and `alembic upgrade head`.

## Step 2: Endpoints

Build them in this order. Each one needs at least one test.

| # | Method and path | Body | Returns |
|---|---|---|---|
| 1 | `POST /api/cabinets` | `{"cabinet_id": "CAB-001", "name": "Line 3 panel"}` | 201 + cabinet; 409 if the id exists |
| 2 | `GET /api/cabinets` | — | list of cabinets with latest inspection status |
| 3 | `GET /api/cabinets/{id}` | — | cabinet + its design revisions |
| 4 | `POST /api/cabinets/{id}/design-revisions` | form: `label`, `drawing` (PDF file) | 201 + revision |
| 5 | `POST /api/design-revisions/{id}/expected-items` | contract A JSON | 201; lets us type the parts list by hand until the drawing parser is ready |
| 6 | `POST /api/cabinets/{id}/inspections` | form: `design_revision_id`, `photos` (1–10 files) | 202 + `{"inspection_id", "state": "queued"}` |
| 7 | `POST /api/inspections/{id}/observations` | contract B JSON (`source: "manual"`) | 201; boxes a person drew on the photo |
| 8 | `POST /api/inspections/{id}/run` | — | 202; runs the engine in the background |
| 9 | `GET /api/inspections/{id}` | — | contract C + `state` (+ `error` if failed) |
| 10 | `GET /api/images/{image_id}` | — | the photo file (used by the frontend `<img>`) |
| 11 | `POST /api/findings/{id}/review` | `{"decision", "reviewer", "note"}` | 201 + event |
| 12 | `POST /api/inspections/{id}/reinspection` | form: `photos` | 202; new inspection with `previous_inspection_id` |
| 13 | `GET /api/cabinets/{id}/quality-passport` | — | all inspections oldest first, with review events |

Error responses always use FastAPI's `{"detail": "plain message"}`; the frontend shows `detail`
to the user.

## Step 3: Running the engine

Task 3 provides one function. Call it; don't copy its logic into the API code:

```python
from backend.app.pipeline.engine import run_inspection   # Task 3

findings, image_flags = run_inspection(
    expected_items=[...],              # list[ExpectedItem] from the database
    observations_by_image={...},       # {"IMG-001": [Observation, ...]}
    image_paths={...},                 # {"IMG-001": "uploads/ab12.jpg"} for photo-quality checks
)
```

Until Task 3 merges `engine.py`, call the existing `compare()` from `pipeline/compare.py`.

Run it with FastAPI's `BackgroundTasks`, so the request returns immediately. Set `state` to
`running`, then `done` or `failed` with the error message. **Always read observations from the
database inside the background task**, never from a list built before it started. (Reusing a stale
list like that caused last time's "everything inconclusive" bug.)

## Step 4: Tests you must add

- Create cabinet → duplicate id gives 409.
- Inspection with zero photos, or a non-image file, gives 400 with a clear message.
- Manual observations → run → `GET` returns at least one `verified` finding (the end-to-end check).
- Review twice → both events kept, status shows the latest.
- Reinspection links to the previous inspection.
- Use pytest's `tmp_path` for the database and uploads, so tests never touch your real files.

## Done when

- [ ] `alembic upgrade head` creates every table on a fresh machine.
- [ ] All 13 endpoints are listed at `/docs` and covered by tests.
- [ ] Full flow works through `/docs` only: create cabinet → add expected items → upload photos →
      add manual boxes → run → see findings → review.
- [ ] `pytest backend/tests -q` passes in CI.
- [ ] `backend/README.md` updated with any new commands.

## Working with the others

- **Task 2 (Frontend)** needs endpoints 1, 2, 6, 9 and 10 first. Tell them as soon as each one is
  merged into `develop`.
- **Task 3 (Engine)** owns `backend/app/pipeline/`. If you need a change there, ask; don't edit it.
- Changing a response shape means updating `docs/contracts.md` and telling Task 2.
- Merge `develop` into your branch daily: `git pull origin develop`.
