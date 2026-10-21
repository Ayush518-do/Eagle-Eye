# Backend

## Run locally

From the repository root:

```bash
python -m venv .venv
# Windows: .venv\\Scripts\\activate
# macOS/Linux: source .venv/bin/activate
pip install -r backend/requirements.txt
uvicorn app.main:app --app-dir backend --reload
```

Health check: http://127.0.0.1:8000/health
API docs: http://127.0.0.1:8000/docs

The current API is a scaffold only. Inspection routes, storage, authentication, and AI inference still need implementation.
