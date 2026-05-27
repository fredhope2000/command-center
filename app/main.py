from __future__ import annotations

from decimal import Decimal, InvalidOperation
from pathlib import Path
from urllib.parse import urlencode

from fastapi import FastAPI, Form, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.auth import (
    AUTH_COOKIE_NAME,
    AuthConfig,
    clear_auth_cookie,
    create_auth_token,
    is_valid_auth_token,
    login_redirect,
    normalize_next_path,
    set_auth_cookie,
    verify_password,
)
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
    auth_config = AuthConfig(
        enabled=settings.auth_enabled,
        password_hash=settings.password_hash,
        secret=settings.auth_secret,
        secure_cookie=settings.is_production,
    )

    if auth_config.enabled and (not auth_config.password_hash or not auth_config.secret):
        raise RuntimeError(
            "COMMAND_CENTER_PASSWORD_HASH and COMMAND_CENTER_AUTH_SECRET are required when auth is enabled."
        )

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

    @app.middleware("http")
    async def require_auth(request: Request, call_next):
        if not auth_config.enabled or _is_public_path(request.url.path):
            return await call_next(request)
        if is_valid_auth_token(
            request.cookies.get(AUTH_COOKIE_NAME),
            auth_config.secret,
        ):
            return await call_next(request)
        return login_redirect(request)

    @app.get("/favicon.ico", include_in_schema=False)
    def favicon() -> RedirectResponse:
        return RedirectResponse(static_asset("favicon.svg"), status_code=307)

    @app.get("/login", include_in_schema=False)
    def login_form(request: Request, next: str = "/"):
        return templates.TemplateResponse(
            request,
            "login.html",
            {
                "next": normalize_next_path(next),
                "error": "",
            },
        )

    @app.post("/login", include_in_schema=False)
    def login(
        password: str = Form(...),
        next: str = Form("/"),
    ) -> RedirectResponse:
        safe_next = normalize_next_path(next)
        if not verify_password(password, auth_config.password_hash):
            response = RedirectResponse(
                f"/login?{urlencode({'next': safe_next})}",
                status_code=303,
            )
            return response
        response = RedirectResponse(safe_next, status_code=303)
        set_auth_cookie(
            response,
            create_auth_token(auth_config.secret),
            secure=auth_config.secure_cookie,
        )
        return response

    @app.post("/logout", include_in_schema=False)
    def logout() -> RedirectResponse:
        response = RedirectResponse("/login", status_code=303)
        clear_auth_cookie(response, secure=auth_config.secure_cookie)
        return response

    app.include_router(pages_router)
    app.include_router(food_router)
    app.include_router(groceries_router)
    app.include_router(recipes_router)
    app.include_router(restaurants_router)
    return app


app = create_app()


def _is_public_path(path: str) -> bool:
    return path in {"/login", "/favicon.ico"} or path.startswith("/static/")
