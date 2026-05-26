from __future__ import annotations

from decimal import Decimal, InvalidOperation
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.db import init_db
from app.routes.food import router as food_router
from app.routes.groceries import router as groceries_router
from app.routes.pages import router as pages_router, templates
from app.routes.recipes import router as recipes_router
from app.routes.restaurants import router as restaurants_router

STATIC_ROOT = Path("app/static")


def create_app() -> FastAPI:
    app = FastAPI(title=settings.app_name)
    app.mount("/static", StaticFiles(directory="app/static"), name="static")

    def static_asset(path: str) -> str:
        asset_path = STATIC_ROOT / path
        version = str(int(asset_path.stat().st_mtime)) if asset_path.exists() else "0"
        return f"/static/{path}?v={version}"

    def compact_number(value: object) -> str:
        if value is None:
            return ""
        try:
            number = Decimal(str(value))
        except (InvalidOperation, ValueError):
            return str(value)
        return format(number.normalize(), "f")

    init_db()
    templates.env.globals["static_asset"] = static_asset
    templates.env.globals["settings"] = settings
    templates.env.filters["compact_number"] = compact_number
    app.include_router(pages_router)
    app.include_router(food_router)
    app.include_router(groceries_router)
    app.include_router(recipes_router)
    app.include_router(restaurants_router)
    return app


app = create_app()
