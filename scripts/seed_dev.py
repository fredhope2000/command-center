from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.db import SessionLocal, init_db
from app.config import settings
from app.models.food import FoodItem, FoodLocation, GroceryPurchase, GroceryPurchaseItem, Recipe


def main() -> None:
    if settings.is_production:
        raise SystemExit("Refusing to seed development data when APP_ENV=production.")

    init_db()
    today = date.today()
    food_rows = [
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
        for row in food_rows:
            if row.name not in existing:
                db.add(row)

        existing_recipes = {recipe.title for recipe in db.query(Recipe).all()}
        if "Lemon chicken bowls" not in existing_recipes:
            db.add(
                Recipe(
                    title="Lemon chicken bowls",
                    source="Family notes",
                    cuisine="Mediterranean",
                    tags="weeknight, high-protein",
                    calories=520,
                    prep_time_minutes=15,
                    cook_time_minutes=25,
                    ingredients="Chicken thighs\nBrown rice\nSpinach\nLemon\nGreek yogurt",
                    instructions="Cook rice. Roast chicken. Wilt spinach. Mix yogurt lemon sauce.",
                    notes="Good candidate for using pantry rice and freezer chicken.",
                )
            )

        existing_purchases = {
            (purchase.store, purchase.purchase_date)
            for purchase in db.query(GroceryPurchase).all()
        }
        purchase_key = ("Trader Joe's", today - timedelta(days=1))
        if purchase_key not in existing_purchases:
            purchase = GroceryPurchase(
                store=purchase_key[0],
                purchase_date=purchase_key[1],
                total_amount=54.28,
                notes="Seed grocery trip for testing.",
            )
            purchase.items = [
                GroceryPurchaseItem(name="Spinach", quantity=1, unit="box", price=3.99),
                GroceryPurchaseItem(name="Greek yogurt", quantity=2, unit="cups", price=5.98),
                GroceryPurchaseItem(name="Lemons", quantity=4, unit="ct", price=2.49),
            ]
            db.add(purchase)
        db.commit()

    print("Seeded development data.")


if __name__ == "__main__":
    main()
