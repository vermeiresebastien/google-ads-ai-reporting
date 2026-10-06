from __future__ import annotations

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from gads.config import get_settings
from gads.db import get_db
from gads.logging import configure_logging
from sqlalchemy import text
from sqlalchemy.orm import Session

from gads_api.routers import actions, analytics, auth, google, platforms


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging()
    if settings.sentry_dsn:
        import sentry_sdk

        sentry_sdk.init(dsn=settings.sentry_dsn, send_default_pii=False)
    app = FastAPI(title="Google Ads AI Reporting", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list(),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["Content-Disposition"],
    )
    app.include_router(auth.router)
    app.include_router(google.router)
    app.include_router(platforms.router)
    app.include_router(analytics.router)
    app.include_router(actions.router)

    @app.get("/", include_in_schema=False)
    def root() -> RedirectResponse:
        return RedirectResponse(settings.frontend_url)

    @app.get("/health")
    def health(session: Session = Depends(get_db)) -> dict:
        session.execute(text("SELECT 1"))
        return {
            "status": "ok",
            "allow_google_mutations": get_settings().allow_google_mutations,
        }

    return app


app = create_app()


def run() -> None:
    import uvicorn

    uvicorn.run("gads_api.main:app", host="0.0.0.0", port=8000, reload=False)
