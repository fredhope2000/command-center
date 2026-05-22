from __future__ import annotations

import re
from datetime import datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.food import (
    FoodItem,
    FoodLocation,
    GroceryPurchase,
    GroceryPurchaseItem,
    Recipe,
    RecipeIngredient,
)

UNIT_FACTORS: dict[str, tuple[str, Decimal]] = {
    "tsp": ("volume", Decimal("1")),
    "teaspoon": ("volume", Decimal("1")),
    "tbsp": ("volume", Decimal("3")),
    "tablespoon": ("volume", Decimal("3")),
    "floz": ("volume", Decimal("6")),
    "fl oz": ("volume", Decimal("6")),
    "cup": ("volume", Decimal("48")),
    "pint": ("volume", Decimal("96")),
    "quart": ("volume", Decimal("192")),
    "gallon": ("volume", Decimal("768")),
    "gal": ("volume", Decimal("768")),
    "ml": ("volume", Decimal("0.202884")),
    "l": ("volume", Decimal("202.884")),
    "oz": ("weight", Decimal("1")),
    "ounce": ("weight", Decimal("1")),
    "lb": ("weight", Decimal("16")),
    "pound": ("weight", Decimal("16")),
    "g": ("weight", Decimal("0.035274")),
    "gram": ("weight", Decimal("0.035274")),
    "kg": ("weight", Decimal("35.274")),
    "ct": ("count", Decimal("1")),
    "count": ("count", Decimal("1")),
    "each": ("count", Decimal("1")),
    "serving": ("count", Decimal("1")),
    "servings": ("count", Decimal("1")),
}

UNIT_ALIASES = {
    "cups": "cup",
    "teaspoons": "teaspoon",
    "tablespoons": "tablespoon",
    "pints": "pint",
    "quarts": "quart",
    "gallons": "gallon",
    "gals": "gal",
    "ounces": "ounce",
    "lbs": "lb",
    "pounds": "pound",
    "grams": "gram",
    "kgs": "kg",
    "counts": "count",
    "items": "each",
}


def normalize_name(value: str) -> str:
    value = re.sub(r"[^a-z0-9\s]", " ", value.lower())
    words = [
        word[:-1] if word.endswith("s") and len(word) > 3 else word
        for word in value.split()
    ]
    return " ".join(words)


def normalize_unit(value: str | None) -> str | None:
    if not value:
        return None
    normalized = re.sub(r"[^a-z\s]", "", value.lower()).strip()
    return UNIT_ALIASES.get(normalized, normalized)


def _conversion_factor(from_unit: str | None, to_unit: str | None) -> Decimal | None:
    from_unit = normalize_unit(from_unit)
    to_unit = normalize_unit(to_unit)
    if from_unit == to_unit:
        return Decimal("1")
    if from_unit is None or to_unit is None:
        return None

    from_info = UNIT_FACTORS.get(from_unit)
    to_info = UNIT_FACTORS.get(to_unit)
    if from_info is None or to_info is None:
        return None
    from_family, from_factor = from_info
    to_family, to_factor = to_info
    if from_family != to_family:
        return None
    return from_factor / to_factor


def conversion_factor(from_unit: str | None, to_unit: str | None) -> Decimal | None:
    return _conversion_factor(from_unit, to_unit)


def _find_matching_inventory_item(
    db: Session, grocery_item: GroceryPurchaseItem
) -> tuple[FoodItem | None, Decimal | None]:
    target_name = normalize_name(grocery_item.name)
    candidates = db.scalars(select(FoodItem).order_by(FoodItem.name.asc())).all()

    for item in candidates:
        if normalize_name(item.name) != target_name:
            continue
        factor = _conversion_factor(grocery_item.unit, item.unit)
        if factor is not None:
            return item, factor
    return None, None


def add_grocery_item_to_inventory(
    db: Session,
    grocery_item: GroceryPurchaseItem,
    purchase: GroceryPurchase,
) -> FoodItem:
    if grocery_item.inventory_item_id is not None:
        existing = db.get(FoodItem, grocery_item.inventory_item_id)
        if existing is not None:
            return existing

    inventory_item, conversion_factor = _find_matching_inventory_item(db, grocery_item)
    if inventory_item is None:
        inventory_item = FoodItem(
            name=grocery_item.name,
            quantity=grocery_item.quantity,
            unit=grocery_item.unit,
            location=FoodLocation.OTHER,
            category=None,
            notes=f"Added from {purchase.store} purchase on {purchase.purchase_date}",
        )
        db.add(inventory_item)
        db.flush()
    else:
        if grocery_item.quantity is not None:
            incoming_quantity = Decimal(str(grocery_item.quantity))
            if conversion_factor is not None:
                incoming_quantity = incoming_quantity * conversion_factor
            if inventory_item.quantity is None:
                inventory_item.quantity = incoming_quantity
            else:
                inventory_item.quantity = Decimal(str(inventory_item.quantity)) + incoming_quantity
        inventory_item.notes = (
            f"Last added from {purchase.store} purchase on {purchase.purchase_date}"
        )

    grocery_item.inventory_item_id = inventory_item.id
    grocery_item.added_to_inventory_at = datetime.utcnow()
    db.commit()
    return inventory_item


def _find_inventory_for_recipe_ingredient(
    db: Session, ingredient: RecipeIngredient
) -> tuple[FoodItem | None, Decimal | None]:
    target_name = normalize_name(ingredient.name)
    candidates = db.scalars(select(FoodItem).order_by(FoodItem.name.asc())).all()

    for item in candidates:
        if normalize_name(item.name) != target_name:
            continue
        factor = _conversion_factor(ingredient.unit, item.unit)
        if ingredient.quantity is None or factor is not None:
            return item, factor
    return None, None


def consume_recipe_ingredients(db: Session, recipe: Recipe) -> None:
    for ingredient in recipe.ingredient_items:
        if ingredient.quantity is None:
            continue
        inventory_item, factor = _find_inventory_for_recipe_ingredient(db, ingredient)
        if inventory_item is None or factor is None or inventory_item.quantity is None:
            continue

        outgoing_quantity = Decimal(str(ingredient.quantity)) * factor
        next_quantity = Decimal(str(inventory_item.quantity)) - outgoing_quantity
        inventory_item.quantity = max(next_quantity, Decimal("0"))
        inventory_item.notes = f"Last used for recipe: {recipe.title}"
