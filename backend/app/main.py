"""Eagle Eye API entry point. Run from the repo root: uvicorn backend.app.main:app --reload"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.app import __version__
from backend.app.api.errors import register_error_handlers
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
    allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$",
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
    expose_headers=["X-Page-Size", "Content-Disposition"],
)


@app.get("/health", tags=["system"])
def health() -> dict[str, str]:
    """Kept for the existing CI check; same as /api/health."""
    return {"status": "ok", "service": "eagle-eye-api", "version": __version__}


register_error_handlers(app)  # every error body is {"detail": "plain message"}
app.include_router(router)
