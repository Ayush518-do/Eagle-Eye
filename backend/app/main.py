"""Eagle Eye API entry point. Run from the repo root: uvicorn backend.app.main:app --reload"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.app import __version__
from backend.app.api.routes import router
from backend.app.config import get_settings

settings = get_settings()

app = FastAPI(
    title="Eagle Eye API",
    description="AI-assisted electrical cabinet inspection prototype",
    version=__version__,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", tags=["system"])
def health() -> dict[str, str]:
    """Kept for the existing CI check; same as /api/health."""
    return {"status": "ok", "service": "eagle-eye-api", "version": __version__}


app.include_router(router)
