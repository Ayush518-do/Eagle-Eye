# Backend (Part 3)

FastAPI service. Task list: [`../docs/team/backend.md`](../docs/team/backend.md).

```text
backend/
├── app/
│   ├── main.py              # app, CORS, /health
│   ├── config.py            # settings from .env
│   ├── schemas.py           # contracts A, B, C (docs/contracts.md)
│   ├── api/routes.py        # /api/health, /api/model/status, POST /api/uploads
│   ├── services/storage.py  # upload checks: real file type, size, safe names, SHA-256
│   └── pipeline/compare.py  # starter tag-based comparison
├── tests/                   # pytest
├── requirements.txt
└── requirements-dev.txt     # + pytest, httpx
```

Run from the repo root:

```bash
pip install -r backend/requirements-dev.txt
uvicorn backend.app.main:app --reload      # http://127.0.0.1:8000/docs
pytest -q
```

## What works now
- `GET /health`, `GET /api/health`
- `GET /api/model/status` — says which models are configured; does not load them
- `POST /api/uploads` — JPEG/PNG/PDF only (checked from file bytes), size limit, generated file names
- `compare()` — matches expected tags to OCR-read tags; unread tags are `inconclusive`, not missing

## Next (see task list)
Database and migrations, inspection endpoints, pipeline service, confidence gate, background runs.
