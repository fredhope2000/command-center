from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.food import FoodItem, GroceryPurchase, Recipe


def get_dashboard_summary(db: Session) -> dict[str, object]:
    today = date.today()
    soon = today + timedelta(days=7)

    expiring_soon = db.scalars(
        select(FoodItem)
        .where(FoodItem.expiration_date.is_not(None))
        .where(FoodItem.expiration_date <= soon)
        .order_by(FoodItem.expiration_date.asc(), FoodItem.name.asc())
        .limit(8)
    ).all()

    recently_added = db.scalars(
        select(FoodItem).order_by(FoodItem.created_at.desc()).limit(6)
    ).all()
    recent_purchases = db.scalars(
        select(GroceryPurchase)
        .order_by(GroceryPurchase.purchase_date.desc(), GroceryPurchase.created_at.desc())
        .limit(5)
    ).all()
    recent_recipes = db.scalars(
        select(Recipe).order_by(Recipe.created_at.desc()).limit(5)
    ).all()

    return {
        "expiring_soon": expiring_soon,
        "recently_added": recently_added,
        "recent_purchases": recent_purchases,
        "recent_recipes": recent_recipes,
    }
