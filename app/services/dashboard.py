from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.food import FoodItem, FoodLocation


def get_dashboard_summary(db: Session) -> dict[str, object]:
    today = date.today()
    soon = today + timedelta(days=7)

    total_items = db.scalar(select(func.count()).select_from(FoodItem)) or 0
    expiring_soon = db.scalars(
        select(FoodItem)
        .where(FoodItem.expiration_date.is_not(None))
        .where(FoodItem.expiration_date <= soon)
        .order_by(FoodItem.expiration_date.asc(), FoodItem.name.asc())
        .limit(8)
    ).all()

    counts_by_location = {
        location.value: db.scalar(
            select(func.count()).select_from(FoodItem).where(FoodItem.location == location)
        )
        or 0
        for location in FoodLocation
    }

    recently_added = db.scalars(
        select(FoodItem).order_by(FoodItem.created_at.desc()).limit(6)
    ).all()

    return {
        "total_items": total_items,
        "expiring_soon": expiring_soon,
        "counts_by_location": counts_by_location,
        "recently_added": recently_added,
    }
