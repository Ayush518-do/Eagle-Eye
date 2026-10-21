"""Minimal FastAPI starter for Eagle Eye.

This is only the service scaffold; inspection endpoints and the ML pipeline are not implemented yet.
"""
from fastapi import FastAPI

app = FastAPI(
    title="Eagle Eye API",
    description="AI-assisted electrical cabinet inspection prototype",
    version="0.1.0",
)


@app.get("/health", tags=["system"])
def health() -> dict[str, str]:
    """Simple endpoint for local smoke tests and future CI."""
    return {"status": "ok", "service": "eagle-eye-api", "version": "0.1.0"}
