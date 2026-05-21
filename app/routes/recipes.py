from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.food import FoodItem, FoodLocation, Recipe
from app.routes.pages import templates
from app.services.recipe_suggestions import suggest_recipes

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
    servings: str = Form(""),
    shelf_life_days: str = Form(""),
    calories_per_serving: str = Form(""),
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
        servings=_parse_optional_int(servings),
        shelf_life_days=_parse_optional_int(shelf_life_days),
        calories_per_serving=_parse_optional_int(calories_per_serving),
        prep_time_minutes=_parse_optional_int(prep_time_minutes),
        cook_time_minutes=_parse_optional_int(cook_time_minutes),
        ingredients=ingredients.strip() or None,
        instructions=instructions.strip() or None,
        notes=notes.strip() or None,
    )
    db.add(recipe)
    db.commit()
    return RedirectResponse("/recipes/", status_code=303)


@router.post("/{recipe_id}")
def update_recipe(
    recipe_id: int,
    title: str = Form(...),
    source: str = Form(""),
    cuisine: str = Form(""),
    tags: str = Form(""),
    servings: str = Form(""),
    shelf_life_days: str = Form(""),
    calories_per_serving: str = Form(""),
    prep_time_minutes: str = Form(""),
    cook_time_minutes: str = Form(""),
    ingredients: str = Form(""),
    instructions: str = Form(""),
    notes: str = Form(""),
    db: Session = Depends(get_db),
):
    recipe = db.get(Recipe, recipe_id)
    if recipe is None:
        return RedirectResponse("/recipes/", status_code=303)

    recipe.title = title.strip()
    recipe.source = source.strip() or None
    recipe.cuisine = cuisine.strip() or None
    recipe.tags = tags.strip() or None
    recipe.servings = _parse_optional_int(servings)
    recipe.shelf_life_days = _parse_optional_int(shelf_life_days)
    recipe.calories_per_serving = _parse_optional_int(calories_per_serving)
    recipe.prep_time_minutes = _parse_optional_int(prep_time_minutes)
    recipe.cook_time_minutes = _parse_optional_int(cook_time_minutes)
    recipe.ingredients = ingredients.strip() or None
    recipe.instructions = instructions.strip() or None
    recipe.notes = notes.strip() or None
    db.commit()
    return RedirectResponse(f"/recipes/{recipe.id}", status_code=303)


@router.post("/{recipe_id}/make")
def make_recipe(recipe_id: int, db: Session = Depends(get_db)):
    recipe = db.get(Recipe, recipe_id)
    if recipe is None:
        return RedirectResponse("/recipes/", status_code=303)

    expiration_date = None
    if recipe.shelf_life_days is not None:
        expiration_date = date.today() + timedelta(days=recipe.shelf_life_days)

    item = FoodItem(
        name=recipe.title,
        quantity=recipe.servings,
        unit="servings",
        location=FoodLocation.FRIDGE,
        category="Prepared meal",
        expiration_date=expiration_date,
        notes=f"Made from recipe: {recipe.title}",
    )
    db.add(item)
    db.commit()
    return RedirectResponse("/food/", status_code=303)


@router.get("/suggestions")
def recipe_suggestions(request: Request, db: Session = Depends(get_db)):
    recipes = db.scalars(select(Recipe).order_by(Recipe.title.asc())).all()
    inventory_items = db.scalars(select(FoodItem).order_by(FoodItem.name.asc())).all()
    return templates.TemplateResponse(
        request,
        "recipes/suggestions.html",
        {
            "active_nav": "recipe_suggestions",
            "suggestion_buckets": suggest_recipes(recipes, inventory_items),
        },
    )


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
