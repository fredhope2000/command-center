from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from app.models.food import FoodItem, Recipe, RecipeIngredient
from app.services.inventory_reconciliation import (
    conversion_factor,
    normalize_name,
)


def _format_quantity(value) -> str:
    quantity = Decimal(str(value))
    if quantity == quantity.to_integral():
        return str(int(quantity))
    return format(quantity.normalize(), "f")


@dataclass(frozen=True)
class IngredientMatch:
    ingredient: RecipeIngredient
    status: str

    @property
    def label(self) -> str:
        parts = []
        if self.ingredient.quantity is not None:
            parts.append(_format_quantity(self.ingredient.quantity))
        if self.ingredient.unit:
            parts.append(self.ingredient.unit)
        parts.append(self.ingredient.name)
        label = " ".join(parts)
        if self.status == "not enough":
            return f"{label} (not enough)"
        return label


@dataclass(frozen=True)
class RecipeSuggestion:
    recipe: Recipe
    ingredients: list[RecipeIngredient]
    matched: list[IngredientMatch]
    missing: list[IngredientMatch]
    score: float

    @property
    def bucket(self) -> str:
        if not self.ingredients:
            return "Needs ingredient list"
        if not self.missing:
            return "Ready to make"
        if self.score >= 0.6:
            return "Almost ready"
        return "Missing several items"


def _legacy_ingredients(recipe: Recipe) -> list[RecipeIngredient]:
    if not recipe.ingredients:
        return []
    return [
        RecipeIngredient(name=line.strip())
        for line in recipe.ingredients.splitlines()
        if line.strip()
    ]


def _recipe_ingredients(recipe: Recipe) -> list[RecipeIngredient]:
    if recipe.ingredient_items:
        return list(recipe.ingredient_items)
    return _legacy_ingredients(recipe)


def _matching_inventory(
    ingredient: RecipeIngredient, inventory_items: list[FoodItem]
) -> tuple[FoodItem | None, Decimal | None]:
    target_name = normalize_name(ingredient.name)
    for item in inventory_items:
        if normalize_name(item.name) != target_name:
            continue
        factor = conversion_factor(ingredient.unit, item.unit)
        if ingredient.quantity is None or factor is not None:
            return item, factor
    return None, None


def _ingredient_status(
    ingredient: RecipeIngredient, inventory_items: list[FoodItem]
) -> IngredientMatch:
    inventory_item, factor = _matching_inventory(ingredient, inventory_items)
    if inventory_item is None:
        return IngredientMatch(ingredient=ingredient, status="missing")
    if ingredient.quantity is None:
        return IngredientMatch(ingredient=ingredient, status="matched")
    if factor is None or inventory_item.quantity is None:
        return IngredientMatch(ingredient=ingredient, status="missing")

    available = Decimal(str(inventory_item.quantity))
    needed = Decimal(str(ingredient.quantity)) * factor
    if available >= needed:
        return IngredientMatch(ingredient=ingredient, status="matched")
    return IngredientMatch(ingredient=ingredient, status="not enough")


def suggest_recipes(
    recipes: list[Recipe], inventory_items: list[FoodItem]
) -> dict[str, list[RecipeSuggestion]]:
    suggestions: list[RecipeSuggestion] = []

    for recipe in recipes:
        ingredients = _recipe_ingredients(recipe)
        statuses = [
            _ingredient_status(ingredient, inventory_items)
            for ingredient in ingredients
        ]
        matched = [status for status in statuses if status.status == "matched"]
        missing = [status for status in statuses if status.status != "matched"]
        score = len(matched) / len(ingredients) if ingredients else 0.0
        suggestions.append(
            RecipeSuggestion(
                recipe=recipe,
                ingredients=ingredients,
                matched=matched,
                missing=missing,
                score=score,
            )
        )

    suggestions.sort(key=lambda suggestion: (-suggestion.score, suggestion.recipe.title))

    buckets = {
        "Ready to make": [],
        "Almost ready": [],
        "Missing several items": [],
        "Needs ingredient list": [],
    }
    for suggestion in suggestions:
        buckets[suggestion.bucket].append(suggestion)
    return buckets
