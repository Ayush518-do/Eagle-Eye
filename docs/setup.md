# Local setup (Windows, macOS, Linux)

You need **Git**, **Python 3.11+** and **Node.js 20+**. Check with:

```bash
git --version
python --version      # Windows: python, macOS/Linux: python3
node --version
```

## 1. Get the code

```bash
git clone https://github.com/Ayush518-do/Eagle-Eye.git
cd Eagle-Eye
git checkout feature/<your-part>     # see docs/team/README.md for your branch
```

## 2. Backend (Part 3, and anyone running the full app)

A *virtual environment* is a private folder of Python packages for this project, so it doesn't clash
with other projects on your computer.

```bash
python -m venv .venv
# Windows PowerShell:
.venv\Scripts\Activate.ps1
# macOS/Linux:
source .venv/bin/activate

pip install -r backend/requirements.txt
copy .env.example .env            # Windows (macOS/Linux: cp .env.example .env)
uvicorn backend.app.main:app --reload
```

Open http://127.0.0.1:8000/health — you should see `{"status": "ok", ...}`.
Interactive API docs are at http://127.0.0.1:8000/docs.

If PowerShell refuses to run `Activate.ps1`, run once:
`Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`.

Run tests: `pytest backend/tests -q` (on the backend branch and later).

## 3. Frontend (Part 4)

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173. The frontend calls the backend at `VITE_API_URL`
(default `http://127.0.0.1:8000`).

## 4. ML (Parts 1 and 2)

Use the same `.venv`, then install your part's extra packages:

```bash
pip install -r ml/requirements-detection.txt   # Part 1
pip install -r ml/requirements-ocr.txt         # Part 2
```

Put company photos and the drawing in `data/private/` (create the folder). Git ignores it.
Check with `git status` that no company file shows up before every commit.

## 5. Before opening a pull request

```bash
git pull origin develop       # get the latest shared work, fix any conflicts
pytest -q                     # backend/ML tests
cd frontend && npm run build  # frontend
```
