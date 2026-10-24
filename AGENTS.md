# Rules for AI coding agents (Codex, Antigravity, Claude, Copilot …)

Eagle Eye compares photos of an electrical cabinet with its approved drawing and reports
missing, unexpected and wrong-rating parts. Read `README.md`, `docs/team/README.md` and
`docs/contracts.md` before changing anything.

## Scope
- Work only on the branch and folders your task file assigns (`docs/team/README.md`, "Owns these folders").
- Never commit to `main` or `develop`, and never force-push. Never rewrite history that is already pushed.
- Shared files (`backend/requirements.txt`, `docs/contracts.md`, `.github/workflows/`) change only when
  the task requires it; say so clearly in your summary.
- Don't rename or move existing files outside your folders.

## Honesty
- Never invent results, metrics, detections, OCR readings or test output. If something can't run, say so.
- Fake data is allowed only for building and testing, must use `"source": "synthetic"` or live in a
  `*.synthetic.json` file, and must never reach a demo result.
- "Not seen in a photo" means `inconclusive`, never `missing`.

## Data
- Never commit company photos, drawings, labels, model weights, `.env`, databases or uploads.
  Company files live in `data/private/` (ignored by Git). Check `git status` before every commit.
- Never upload company files to any external service.

## Workflow
1. Read your task file in `docs/team/` fully before writing code.
2. Do one step of the task file at a time. After each step: run the tests, commit with a clear message,
   and report what changed and what the test output was.
3. Every new behaviour gets a test. Run before committing:
   - backend/engine: `pytest backend/tests -q`
   - ML: `pytest ml/tests -q`
   - frontend: `cd frontend && npm run build`
4. Follow the data shapes in `docs/contracts.md` and `backend/app/schemas.py` exactly.
5. Ask the human before: adding a dependency, changing a contract, deleting files, or anything outside your folders.

## Commands
```bash
pip install -r backend/requirements-dev.txt
uvicorn backend.app.main:app --reload        # API on http://127.0.0.1:8000/docs
cd frontend && npm install && npm run dev    # UI on http://localhost:5173
```
