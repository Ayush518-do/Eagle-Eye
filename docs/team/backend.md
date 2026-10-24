# Task 1: Backend (API and database): complete guide

**Branch:** `feature/backend-pipeline`
**You own:** `backend/app/` (except `backend/app/pipeline/` and `backend/app/reports/`), `backend/alembic/`,
`backend/tests/` (except `test_engine_*.py` and `test_compare.py`), `backend/requirements*.txt`, `backend/README.md`.
**Don't edit:** `backend/app/pipeline/`, `backend/app/reports/` (Task 3), `frontend/` (Task 2), `ml/`.

This file covers your work **until the project is finished**. Work through the milestones in order.
Each step ends with a check you can run yourself. If something here is unclear or blocked, tell the
team lead; don't guess.

---

## 0. What you're building, in one picture

```text
Frontend ──HTTP──► Backend API ──► SQLite database + uploads/ folder
                       │
                       ├──► Engine (Task 3): run_inspection(...)   → findings, arrangement, photo flags
                       ├──► Engine (Task 3): analytics / CSV / report helpers
                       └──► ml/interfaces.py (Phase 2)             → observations from the models
```

The backend is the **middle**. It stores everything and moves data between the screens, the engine and
the models. It contains **no inspection rules**: those live in the engine.

The data shapes you send and receive are fixed in **`docs/contracts.md` (version 0.2)**. Read it before
starting. `backend/app/schemas.py` must match it.

## 1. What already exists (don't rebuild)

| File | Does |
|---|---|
| `app/main.py` | Creates the app; allows the frontend to call it (CORS) |
| `app/config.py` | Settings from `.env` |
| `app/schemas.py` | Data shapes for contract 0.1 (you update them to 0.2 in M1) |
| `app/api/routes.py` | `GET /api/health`, `GET /api/model/status`, `POST /api/uploads` |
| `app/services/storage.py` | Safe file saving: checks the real file type, size limit, generated names |
| `app/pipeline/compare.py` | Starter comparison (owned by Task 3; you only call it) |
| `tests/` | 13 tests: `pytest backend/tests -q` |

Run it: `uvicorn backend.app.main:app --reload`, then open http://127.0.0.1:8000/docs.

---

## Milestone 1: Core flow (must have, do first)

### 1.1 Update schemas to contract 0.2
Add to `app/schemas.py`:

- `ExpectedItem.component_type` and `ExpectedItem.arrangement` (`group`, `position`, `direction`)
- `Observation.source` includes `zero_shot`; `Observation.kind` includes `rating_text`
- `Finding.component_type`, `sources`, `evidence_score`, `reviews`; types `order_changed`, `type_mismatch`
- `ArrangementResult` and `InspectionResult.arrangement`, `state`, `error`, `previous_inspection_id`
- `AnalyticsResult` (contract section D)

**Check:** add a test that loads the JSON examples from `docs/contracts.md` into these models without errors.

### 1.2 Database
**SQLAlchemy 2** lets you work with Python classes instead of writing SQL. **Alembic** keeps a
numbered history of table changes (*migrations*), so everyone's database has the same tables.

```bash
pip install "sqlalchemy>=2,<3" "alembic>=1.13,<2"      # add both to backend/requirements.txt
alembic init backend/alembic
```

Tables (`backend/app/models.py`):

| Table | Columns |
|---|---|
| `cabinets` | `id` (e.g. `CAB-001`), `name`, `created_at` |
| `design_revisions` | `id`, `cabinet_id`, `label`, `drawing_file_id`, `drawing_sha256`, `created_at` |
| `expected_items` | `id`, `design_revision_id`, `tag`, `component_type`, `part_number`, `description`, `quantity`, `rating_value`, `rating_needs_review`, `arrangement_group`, `arrangement_position`, `arrangement_direction` |
| `inspections` | `id`, `cabinet_id`, `design_revision_id`, `state`, `error`, `overall_status`, `previous_inspection_id`, `created_at` |
| `images` | `id`, `inspection_id`, `file_id`, `sha256`, `width`, `height`, `quality_flags` (JSON) |
| `observations` | `id`, `image_id`, `source`, `kind`, `class_name`, `bbox` (JSON), `confidence`, `text`, `raw_text`, `text_confidence`, `model` (JSON) |
| `findings` | `id`, `inspection_id`, `type`, `tag`, `component_type`, `expected_value`, `observed_text`, `detector_confidence`, `ocr_confidence`, `sources` (JSON), `evidence_score`, `status`, `reason`, `evidence` (JSON) |
| `arrangement_results` | `id`, `inspection_id`, `group`, `direction`, `expected_order` (JSON), `observed_order` (JSON), `out_of_order` (JSON), `status` |
| `review_events` | `id`, `finding_id`, `decision`, `reviewer`, `note`, `created_at` |

**Rule:** never update or delete `review_events` rows. A finding's current status = its original status,
overridden by the newest review event.

```python
# backend/app/models.py (pattern for every table)
from datetime import datetime, timezone
from sqlalchemy import String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

class Base(DeclarativeBase):
    pass

class Cabinet(Base):
    __tablename__ = "cabinets"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc))
```

```bash
alembic revision --autogenerate -m "initial tables"
alembic upgrade head
```

**Check:** delete `eagle_eye.db`, run `alembic upgrade head`; all 9 tables exist.

### 1.3 Core endpoints (build in this order; each needs a test)

| # | Method and path | Body | Returns |
|---|---|---|---|
| 1 | `POST /api/cabinets` | `{"cabinet_id","name"}` | 201; 409 if the id exists |
| 2 | `GET /api/cabinets` | — | list, each with its latest inspection status |
| 3 | `GET /api/cabinets/{id}` | — | cabinet + design revisions |
| 4 | `POST /api/cabinets/{id}/design-revisions` | form: `label`, `drawing` (PDF) | 201 + revision |
| 5 | `POST /api/design-revisions/{id}/expected-items` | contract A | 201; replaces the list for that revision |
| 6 | `GET /api/design-revisions/{id}/expected-items` | — | contract A |
| 7 | `POST /api/cabinets/{id}/inspections` | form: `design_revision_id`, `photos` (1–10) | 202 `{"inspection_id","state":"queued"}` |
| 8 | `POST /api/inspections/{id}/observations` | contract B (`manual`) | 201 |
| 9 | `GET /api/inspections/{id}/observations` | — | contract B per image |
| 10 | `POST /api/inspections/{id}/run` | — | 202; runs the engine in the background |
| 11 | `GET /api/inspections/{id}` | — | contract C |
| 12 | `GET /api/images/{image_id}` | — | the photo file |
| 13 | `POST /api/findings/{id}/review` | review decision | 201 + event |

Errors always use `{"detail": "plain message"}`. The frontend shows `detail` to the user.

Tell **Task 2** when endpoints 1, 2, 7, 11 and 12 are merged into `develop`. They need those first.

### 1.4 Running the engine
Call Task 3's single function; don't copy its logic:

```python
from backend.app.pipeline.engine import run_inspection

result = run_inspection(
    expected_items=expected,             # list[ExpectedItem] from the database
    observations_by_image=observations,  # {"IMG-001": [Observation, ...]} read from the database NOW
    image_paths=paths,                   # {"IMG-001": "uploads/ab12.jpg"}
)
# result.findings, result.arrangement, result.image_flags, result.overall_status, result.counts
```

Until Task 3 merges `engine.py`, call `compare()` from `pipeline/compare.py`.

Run it with FastAPI `BackgroundTasks`. Set `state` to `running`, then `done`, or `failed` with the error text.
**Read observations from the database inside the background task.** Never use a list built before
the task started. A stale list like that caused an earlier prototype to mark every finding "inconclusive".

**Check (end-to-end test):** create cabinet → expected items CB11, CB12 → upload 1 photo → manual tag
observation "CB11" → run → `GET` shows CB11 `verified` and CB12 `inconclusive`.

### 1.5 CI
`pytest backend/tests -q` must pass on GitHub for every push. Use pytest's `tmp_path` for the
database and uploads in tests.

---

## Milestone 2: Selected features (high priority)

| # | Method and path | Purpose | Notes |
|---|---|---|---|
| 14 | `POST /api/inspections/{id}/reinspection` | Inspect again after a fix | New inspection with `previous_inspection_id`; engine compares old vs new |
| 15 | `GET /api/cabinets/{id}/quality-passport` | Inspection history | All inspections oldest first, with findings counts and review events |
| 16 | `GET /api/inspections/{id}/report` | Readable report (HTML) | Calls Task 3's `render_report(...)`, returns `text/html` |
| 17 | `GET /api/inspections/{id}/export.csv` | Export findings | Calls Task 3's `findings_to_csv(...)`; `Content-Disposition: attachment` |
| 18 | `PATCH /api/findings/{id}` | Not allowed | Return 405: findings are only changed through review events |

**Check:** a reinspection where CB12 is now read → old CB12 shows `resolved_after_reinspection` in the
passport, and the old finding row is unchanged.

## Milestone 3: Extras (medium priority, after M1–M2 work end to end)

| # | Method and path | Purpose |
|---|---|---|
| 19 | `GET /api/analytics?from=&to=` | Contract D. Calls Task 3's `summarise(...)` on the stored findings |
| 20 | `GET /api/cabinets/{id}/qr` | PNG QR code (a printable square barcode) linking to `{FRONTEND_URL}/cabinets/{id}`. Use `pip install qrcode[pil]` |
| 21 | `GET /api/inspections?cabinet_id=&status=` | List and filter inspections for the dashboard |

Add `FRONTEND_URL=http://localhost:5173` to `.env.example`.

## Milestone 4: ML integration (when the ML branches are merged)

1. In the run task, call `ml.interfaces.detect_components()` and `read_tags()` for each photo. Store
   their observations next to the manual ones. Catch `ModelUnavailableError` and record it in
   `GET /api/model/status`, so the run continues with whatever sources exist.
2. On drawing upload, if `parse_drawing()` is available, fill the expected items automatically
   and mark them "from parser". The parts editor still lets a person correct them.
3. `GET /api/model/status` reports each model: available or not, version, weights checksum.

**Check:** with no models installed, everything still works on manual boxes. With models, findings show
`sources` that include `ocr` and `detector`.

## Milestone 5: Demo hardening

- Seed script `backend/scripts/seed_demo.py` creates the demo cabinet, revision and expected items
  (from the parser, or a JSON file in `data/private/`). It reads company files only from `data/private/`.
- Uploads over the limit, non-images and missing revisions give clear 400 messages.
- `/docs` page tidy: every endpoint has a one-line summary.
- Timing: log how long each run takes; it shows in `GET /api/inspections/{id}` as `duration_seconds`.
- README: exact commands to set up, migrate, seed and run.

---

## Tests you must have by the end

- Create cabinet; duplicate gives 409.
- Inspection with 0 photos, 11 photos, or a non-image gives 400.
- End-to-end with manual observations gives at least one `verified` finding.
- Two reviews on one finding: both kept, current status = newest.
- Reinspection links to the previous one; the old finding is unchanged.
- CSV export has a header row and one row per finding.
- Analytics counts match the stored findings.
- Model unavailable: run still completes, and `model/status` explains why.

## Done when

- [ ] All endpoints 1–21 exist, appear at `/docs` and have tests.
- [ ] Full flow works using only `/docs`, with no frontend.
- [ ] `alembic upgrade head` works on a fresh machine; the seed script runs.
- [ ] CI is green.
- [ ] The README is updated.

## Working with the others

- **Frontend (Task 2):** tell them as each endpoint lands in `develop`. If you must change a response,
  update `docs/contracts.md` first and tell them.
- **Engine (Task 3):** you call `run_inspection`, `render_report`, `findings_to_csv` and `summarise`.
  You don't edit their files. If you need a change, ask.
- Merge `develop` into your branch daily: `git pull origin develop`. Open a pull request into `develop`
  at the end of each milestone.
