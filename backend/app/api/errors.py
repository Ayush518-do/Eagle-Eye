"""Error bodies. The task guide requires every error as {"detail": "plain message"}.

FastAPI's own validation errors carry a list in `detail`; this turns them into one plain string
that names the field and the problem. It never includes the submitted value, a traceback or a
file path. Anything unexpected becomes a generic 500 and is logged on the server only.
"""
import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

log = logging.getLogger(__name__)

_SOURCES = {"body", "query", "path", "form", "header", "cookie"}
MAX_ERRORS_SHOWN = 5


def validation_message(errors: list[dict]) -> str:
    if any(e.get("type") == "json_invalid" for e in errors):
        return "The request body is not valid JSON."
    parts = []
    for e in errors[:MAX_ERRORS_SHOWN]:
        where = ".".join(str(p) for p in e.get("loc", ()) if p not in _SOURCES)
        msg = str(e.get("msg", "Invalid value")).removeprefix("Value error, ")
        if e.get("type") == "missing" and not where:
            parts.append("The request body is required.")
        else:
            parts.append(f"{where or 'request body'}: {msg}")
    if len(errors) > MAX_ERRORS_SHOWN:
        parts.append(f"and {len(errors) - MAX_ERRORS_SHOWN} more problem(s)")
    return "; ".join(parts)


async def _validation_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(status_code=422, content={"detail": validation_message(exc.errors())})


async def _unexpected_handler(_: Request, exc: Exception) -> JSONResponse:
    log.exception("Unhandled error", exc_info=exc)
    return JSONResponse(status_code=500, content={"detail": "Internal server error."})


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(RequestValidationError, _validation_handler)
    app.add_exception_handler(Exception, _unexpected_handler)
