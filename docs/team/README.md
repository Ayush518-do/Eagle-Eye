# Team work split

Work runs in two phases. **Phase 1 (now)** has three tasks that don't need ML.
**Phase 2** adds the two ML tasks once the ML documents arrive.

## Phase 1: start now

| Task | Owner | Branch | Instructions | Owns these folders |
|---|---|---|---|---|
| 1. Backend: API and database | _TBD_ | `feature/backend-pipeline` | [backend.md](backend.md) | `backend/app/` (not `pipeline/`), `backend/alembic/` |
| 2. Frontend: screens | _TBD_ | `feature/frontend-ui` | [frontend.md](frontend.md) | `frontend/`, `tests/e2e/` |
| 3. Inspection engine: rules, photo quality, reports | _TBD_ | `feature/inspection-engine` | [inspection-engine.md](inspection-engine.md) | `backend/app/pipeline/`, `backend/app/reports/`, `config/` |

Each task owns different folders, so two people rarely edit the same file. Shared files
(`backend/requirements.txt`, `docs/contracts.md`) need a quick message to the others before you change them.

Until ML exists, photos get **manual boxes**: a person draws a box on the photo and types the tag
(`"source": "manual"`). Backend, frontend and engine can all be finished and tested this way.

## Phase 2: ML (after the documents arrive)

| Task | Owner | Branch | Instructions |
|---|---|---|---|
| 4. Component detection | _TBD_ | `feature/ml-detection` | [ml-detection.md](ml-detection.md) |
| 5. Drawing parser and tag reading (OCR) | _TBD_ | `feature/ml-ocr-drawing` | [ml-ocr-drawing.md](ml-ocr-drawing.md) |

Team: Ayush, Pranay, Aditya, Archita. Fill in the Owner columns once tasks are assigned.

First-time setup: [`../setup.md`](../setup.md).

## How the parts connect

```text
 drawing PDF ──(Task 5, or typed by hand)──► expected items ─────────┐
                                                                     ▼
 photos ──(Tasks 4+5, or manual boxes)──► observations ──► Task 3 engine ──► findings
                                                                     │
                     Task 1: API + database stores everything ◄──────┘
                                       │
                                       ▼
                              Task 2: screens
```

The two hand-over formats are fixed in [`../contracts.md`](../contracts.md). Parts can work at the same
time because each side codes against that file, not against the other team's code.

## Branches

- `main` — what we demo. Only changed by merging `develop` after the team agrees.
- `develop` — the shared integration branch. Every feature branch is merged into `develop` through a
  pull request once its tests pass.
- `feature/*` — one per part, created from `develop`.

### Daily routine

```bash
git checkout feature/<your-part>
git pull origin develop          # pick up everyone else's merged work
# ...work, commit...
git push origin feature/<your-part>
# open a pull request: feature/<your-part> -> develop
```

### Rules

1. Never push directly to `main` or `develop`; use pull requests.
2. Changing `docs/contracts.md` needs agreement from the parts on both sides of that hand-over.
3. Company photos, the drawing PDF, labels made from them and trained weights never go into Git.
   Keep them in `data/private/` (ignored by Git) and share them through the team's agreed channel.
4. No invented results. Sample data used while waiting for another part must be labelled
   `"source": "synthetic"` and must never appear in a demo result or a metric.
5. Report only numbers produced by a script, and say what data they were measured on.

## Current status

- `develop` contains tested starters for every task: backend API basics (13 tests), frontend screens
  (builds), comparison starter, and ML tools (14 tests). Details are in each task file.
- There's no database and no inspection endpoints yet; Task 1 starts there.
- Known results from that prototype, for reference only (one reviewer, development photos, not an
  independent test): RapidOCR read 12/12 hand-marked tags exactly, Tesseract 5/12; the drawing parser
  read all 70 BOM lines; power-supply ratings PS11–PS23 could not be read reliably.
- No detector has been trained. There are no labels yet.
