"""FastAPI app factory."""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from .routes.recipes import router as recipes_router
from .security import SecurityMiddleware, SessionSecurity

log = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).resolve().parent / "static"


def create_app(*, session: SessionSecurity) -> FastAPI:
    """Build the FastAPI app with security middleware + static mount.

    `session` is required — `understudy ui` mints one at startup. Callers
    in tests should construct a throw-away `SessionSecurity`.
    """
    app = FastAPI(
        title="Understudy",
        version="0.2.0",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )

    app.add_middleware(SecurityMiddleware, session=session)
    app.include_router(recipes_router)

    # Serve the built frontend when present; otherwise serve a placeholder
    # index that tells the developer to run the build script.
    if (STATIC_DIR / "index.html").exists():
        app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="ui")
    else:

        @app.get("/", include_in_schema=False)
        async def _missing_ui() -> dict[str, str]:
            return {
                "error": "frontend not built",
                "hint": "run `./scripts/build-ui.sh` or see docs/",
            }

    return app
