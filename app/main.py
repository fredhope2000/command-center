from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.db import init_db
from app.routes.food import router as food_router
from app.routes.pages import router as pages_router, templates

STATIC_ROOT = Path("app/static")


def create_app() -> FastAPI:
    app = FastAPI(title=settings.app_name)
    app.mount("/static", StaticFiles(directory="app/static"), name="static")

    def static_asset(path: str) -> str:
        asset_path = STATIC_ROOT / path
        version = str(int(asset_path.stat().st_mtime)) if asset_path.exists() else "0"
        return f"/static/{path}?v={version}"

    init_db()
    templates.env.globals["static_asset"] = static_asset
    templates.env.globals["settings"] = settings
    app.include_router(pages_router)
    app.include_router(food_router)
    return app


app = create_app()
