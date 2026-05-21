from __future__ import annotations

import re
from dataclasses import dataclass

from app.models.food import FoodItem, Recipe

STOP_WORDS = {
    "and",
    "as",
    "chopped",
    "clove",
    "cloves",
    "cup",
    "cups",
    "diced",
    "for",
    "fresh",
    "large",
    "lb",
    "lbs",
    "medium",
    "minced",
    "of",
    "optional",
    "oz",
    "small",
    "tbsp",
    "tsp",
    "to",
}


@dataclass(frozen=True)
class RecipeSuggestion:
    recipe: Recipe
    ingredients: list[str]
    matched: list[str]
    missing: list[str]
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


def _normalize(value: str) -> str:
    value = re.sub(r"[^a-z0-9\s]", " ", value.lower())
    words = [
        word[:-1] if word.endswith("s") and len(word) > 3 else word
        for word in value.split()
        if not word.isdigit() and word not in STOP_WORDS
    ]
    return " ".join(words).strip()


def _parse_ingredients(ingredients: str | None) -> list[str]:
    if not ingredients:
        return []

    parsed: list[str] = []
    for raw_line in ingredients.splitlines():
        line = _normalize(raw_line)
        if line:
            parsed.append(line)
    return parsed


def _inventory_terms(items: list[FoodItem]) -> set[str]:
    terms: set[str] = set()
    for item in items:
        for value in (item.name, item.category):
            if not value:
                continue
            normalized = _normalize(value)
            if normalized:
                terms.add(normalized)
    return terms


def _is_matched(ingredient: str, inventory_terms: set[str]) -> bool:
    ingredient_words = set(ingredient.split())
    for term in inventory_terms:
        term_words = set(term.split())
        if ingredient in term or term in ingredient:
            return True
        if ingredient_words and ingredient_words.issubset(term_words):
            return True
        if term_words and term_words.issubset(ingredient_words):
            return True
    return False


def suggest_recipes(
    recipes: list[Recipe], inventory_items: list[FoodItem]
) -> dict[str, list[RecipeSuggestion]]:
    inventory_terms = _inventory_terms(inventory_items)
    suggestions: list[RecipeSuggestion] = []

    for recipe in recipes:
        ingredients = _parse_ingredients(recipe.ingredients)
        matched = [
            ingredient
            for ingredient in ingredients
            if _is_matched(ingredient, inventory_terms)
        ]
        missing = [
            ingredient
            for ingredient in ingredients
            if ingredient not in matched
        ]
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
