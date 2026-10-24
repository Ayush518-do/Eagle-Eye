# Part 3 — Backend: API, database, comparison, pipeline

Branch: `feature/backend-pipeline` · Folder: `backend/` · Consumes: contracts A and B · Produces: contract C

**Goal:** accept uploads, call Parts 1 and 2 through `ml/interfaces.py`, compare expected items with
what was seen, store everything, and serve results to the frontend.

## Tasks

- [ ] 1. `backend/app/config.py` (settings from `.env`), `schemas.py` (Pydantic models for contracts A, B, C).
- [ ] 2. Keep `GET /health`; add `GET /api/health` and `GET /api/model/status`
      (which models are loaded, or why not).
- [ ] 3. Upload endpoint with validation: allowed types (JPEG, PNG, PDF), size limit, safe file names,
      SHA-256 stored per file.
- [ ] 4. Database (SQLite + SQLAlchemy + Alembic migrations): cabinets, design revisions, expected items,
      inspections, images, observations, findings, review events (append-only).
- [ ] 5. `backend/app/pipeline/compare.py`: match observations to expected items by tag first, then by
      position. Produce findings per contract C.
- [ ] 6. Confidence gate: below agreed thresholds, or on a blurry image, the finding becomes
      `needs_review` or `inconclusive` — never `missing`.
- [ ] 7. Pipeline service that runs detection + OCR + comparison for an inspection.
      **Known bug from the prototype:** the loop used a stale cached list of observations per photo, so
      75 stored detections never reached the comparison and every finding was `inconclusive`.
      Read observations fresh from the database (or from the return value) before comparing, and add a
      test that would have caught it: real detector observations in, at least one non-inconclusive finding out.
- [ ] 8. Endpoints from `docs/api-contract.md`: cabinets, design revisions, inspections, review, reinspection,
      quality passport.
- [ ] 9. Run long inspections in the background (FastAPI background task) and expose a status field;
      a CPU run on 4 photos took about 11 minutes.
- [ ] 10. Tests with `pytest`: health, upload validation, model-unavailable error, comparison rules,
      review history kept. Update `.github/workflows/tests.yml` to run them.
- [ ] 11. Until Parts 1 and 2 deliver, use fixtures marked `"source": "synthetic"` in tests only.

## Done when

- One real end-to-end run on the company photos gives findings from real observations, not all inconclusive.
- All tests pass in CI, and the README lists the exact run commands.
