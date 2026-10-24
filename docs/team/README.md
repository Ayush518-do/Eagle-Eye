# Team work split

Eagle Eye is divided into four parts. Each part has one owner, one branch and one task list.

| Part | Owner | Branch | Task list |
|---|---|---|---|
| 1. Vision / component detection (ML) | _TBD_ | `feature/ml-detection` | [part1-ml-detection.md](part1-ml-detection.md) |
| 2. Drawing parser and OCR (ML) | _TBD_ | `feature/ml-ocr-drawing` | [part2-ml-ocr-drawing.md](part2-ml-ocr-drawing.md) |
| 3. Backend: API, database, comparison, pipeline | _TBD_ | `feature/backend-pipeline` | [part3-backend.md](part3-backend.md) |
| 4. Frontend: upload, results, review, history | _TBD_ | `feature/frontend-ui` | [part4-frontend.md](part4-frontend.md) |

Team: Ayush, Pranay, Aditya, Archita. Fill in the Owner column once parts are assigned.

First-time setup: [`../setup.md`](../setup.md).

## How the parts connect

```text
 Part 2: drawing PDF ──► expected items (tags, part numbers, ratings)
                                   │
 Part 1: photo ──► component boxes │
 Part 2: photo ──► tag text read   │
                     │             ▼
                     └──► Part 3: comparison + database + API ──► Part 4: screens
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

## Status at the time of the split

- The repository is still the starter scaffold (`/health` endpoint and a static upload page).
- Earlier prototype work (drawing parser, OCR wrappers, comparison engine, database, React workflow)
  was never committed and is not in this repository. Each task list says what has to be rebuilt.
- Known results from that prototype, for reference only (one reviewer, development photos, not an
  independent test): RapidOCR read 12/12 hand-marked tags exactly, Tesseract 5/12; the drawing parser
  read all 70 BOM lines; power-supply ratings PS11–PS23 could not be read reliably.
- No detector has been trained. There are no labels yet.
