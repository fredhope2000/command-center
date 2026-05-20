from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.db import SessionLocal, init_db
from app.config import settings
from app.models.food import FoodItem, FoodLocation


def main() -> None:
    if settings.is_production:
        raise SystemExit("Refusing to seed development data when APP_ENV=production.")

    init_db()
    today = date.today()
    rows = [
        FoodItem(
            name="Greek yogurt",
            quantity=2,
            unit="cups",
            location=FoodLocation.FRIDGE,
            category="Dairy",
            expiration_date=today + timedelta(days=5),
            notes="Good for breakfast bowls.",
        ),
        FoodItem(
            name="Chicken thighs",
            quantity=1,
            unit="pack",
            location=FoodLocation.FREEZER,
            category="Protein",
            notes="Use for sheet-pan dinner.",
        ),
        FoodItem(
            name="Brown rice",
            quantity=1,
            unit="bag",
            location=FoodLocation.PANTRY,
            category="Staple",
        ),
        FoodItem(
            name="Spinach",
            quantity=1,
            unit="box",
            location=FoodLocation.FRIDGE,
            category="Produce",
            expiration_date=today + timedelta(days=3),
        ),
    ]

    with SessionLocal() as db:
        existing = {item.name for item in db.query(FoodItem).all()}
        for row in rows:
            if row.name not in existing:
                db.add(row)
        db.commit()

    print("Seeded development data.")


if __name__ == "__main__":
    main()
