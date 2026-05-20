from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.food import Recipe
from app.routes.pages import templates

router = APIRouter(prefix="/recipes", tags=["recipes"])


def _parse_optional_int(value: str) -> int | None:
    value = value.strip()
    if not value:
        return None
    return int(value)


@router.get("/")
def list_recipes(request: Request, db: Session = Depends(get_db)):
    recipes = db.scalars(select(Recipe).order_by(Recipe.title.asc())).all()
    return templates.TemplateResponse(
        request,
        "recipes/index.html",
        {"active_nav": "recipes", "recipes": recipes},
    )


@router.post("/")
def create_recipe(
    title: str = Form(...),
    source: str = Form(""),
    cuisine: str = Form(""),
    tags: str = Form(""),
    calories: str = Form(""),
    prep_time_minutes: str = Form(""),
    cook_time_minutes: str = Form(""),
    ingredients: str = Form(""),
    instructions: str = Form(""),
    notes: str = Form(""),
    db: Session = Depends(get_db),
):
    recipe = Recipe(
        title=title.strip(),
        source=source.strip() or None,
        cuisine=cuisine.strip() or None,
        tags=tags.strip() or None,
        calories=_parse_optional_int(calories),
        prep_time_minutes=_parse_optional_int(prep_time_minutes),
        cook_time_minutes=_parse_optional_int(cook_time_minutes),
        ingredients=ingredients.strip() or None,
        instructions=instructions.strip() or None,
        notes=notes.strip() or None,
    )
    db.add(recipe)
    db.commit()
    return RedirectResponse("/recipes/", status_code=303)


@router.get("/{recipe_id}")
def recipe_detail(recipe_id: int, request: Request, db: Session = Depends(get_db)):
    recipe = db.get(Recipe, recipe_id)
    if recipe is None:
        return RedirectResponse("/recipes/", status_code=303)
    return templates.TemplateResponse(
        request,
        "recipes/detail.html",
        {"active_nav": "recipes", "recipe": recipe},
    )


@router.post("/{recipe_id}/delete")
def delete_recipe(recipe_id: int, db: Session = Depends(get_db)):
    recipe = db.get(Recipe, recipe_id)
    if recipe is not None:
        db.delete(recipe)
        db.commit()
    return RedirectResponse("/recipes/", status_code=303)
