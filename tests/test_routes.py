from __future__ import annotations

import importlib
import sys
from collections.abc import Iterator

from fastapi.testclient import TestClient
import pytest


@pytest.fixture()
def client(tmp_path, monkeypatch) -> Iterator[TestClient]:
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'test.sqlite'}")
    monkeypatch.delenv("GOOGLE_MAPS_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_MAPS_MAP_ID", raising=False)
    for name in list(sys.modules):
        if name == "app" or name.startswith("app."):
            sys.modules.pop(name)

    main = importlib.import_module("app.main")
    with TestClient(main.app) as test_client:
        yield test_client


def test_dashboard_renders(client: TestClient) -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert "Dashboard" in response.text


def test_food_inventory_renders(client: TestClient) -> None:
    response = client.get("/food/")

    assert response.status_code == 200
    assert "Food Inventory" in response.text


def test_food_item_can_be_created(client: TestClient) -> None:
    response = client.post(
        "/food/",
        data={
            "name": "Test apples",
            "quantity": "3",
            "unit": "ct",
            "location": "fridge",
            "category": "Produce",
            "expiration_date": "",
            "notes": "",
        },
        follow_redirects=False,
    )

    assert response.status_code == 303

    update_response = client.post(
        "/food/1",
        data={
            "name": "Updated apples",
            "quantity": "2",
            "unit": "ct",
            "location": "pantry",
            "category": "Fruit",
            "expiration_date": "2026-05-30",
            "notes": "Move after washing",
        },
        follow_redirects=False,
    )
    assert update_response.status_code == 303

    list_response = client.get("/food/")
    assert list_response.status_code == 200
    assert "Updated apples" in list_response.text
    assert "Move after washing" in list_response.text


def test_grocery_purchase_can_be_created(client: TestClient) -> None:
    response = client.post(
        "/groceries/",
        data={
            "store": "Test market",
            "purchase_date": "2026-05-20",
            "total_amount": "12.34",
            "notes": "",
            "item_name": ["Bananas", "Greek yogurt"],
            "item_quantity": ["6", "2"],
            "item_unit": ["ct", "cups"],
            "item_price": ["2.49", "5.99"],
            "item_notes": ["", "Plain"],
        },
        follow_redirects=False,
    )

    assert response.status_code == 303

    detail_response = client.get("/groceries/1")
    assert detail_response.status_code == 200
    assert "Bananas" in detail_response.text
    assert "Greek yogurt" in detail_response.text


def test_grocery_purchase_and_line_item_can_be_edited(client: TestClient) -> None:
    create_response = client.post(
        "/groceries/",
        data={
            "store": "Test market",
            "purchase_date": "2026-05-20",
            "total_amount": "12.34",
            "notes": "",
        },
        follow_redirects=False,
    )
    assert create_response.status_code == 303

    update_purchase_response = client.post(
        "/groceries/1",
        data={
            "store": "Updated market",
            "purchase_date": "2026-05-21",
            "total_amount": "22.50",
            "notes": "Updated notes",
        },
        follow_redirects=False,
    )
    assert update_purchase_response.status_code == 303

    add_item_response = client.post(
        "/groceries/1/items",
        data={
            "name": "Bananas",
            "quantity": "6",
            "unit": "ct",
            "price": "2.49",
            "notes": "",
        },
        follow_redirects=False,
    )
    assert add_item_response.status_code == 303

    update_item_response = client.post(
        "/groceries/1/items/1",
        data={
            "name": "Apples",
            "quantity": "4",
            "unit": "ct",
            "price": "3.99",
            "notes": "Honeycrisp",
        },
        follow_redirects=False,
    )
    assert update_item_response.status_code == 303

    detail_response = client.get("/groceries/1")
    assert detail_response.status_code == 200
    assert "Updated market" in detail_response.text
    assert "22.50" in detail_response.text
    assert "Apples" in detail_response.text
    assert "Honeycrisp" in detail_response.text


def test_grocery_purchase_detail_can_save_all_edits_and_remove_item(
    client: TestClient,
) -> None:
    client.post(
        "/groceries/",
        data={
            "store": "Test market",
            "purchase_date": "2026-05-20",
            "total_amount": "12.34",
            "notes": "",
            "item_name": ["Bananas", "Milk"],
            "item_quantity": ["6", "1"],
            "item_unit": ["ct", "gal"],
            "item_price": ["2.49", "4.99"],
            "item_notes": ["", ""],
        },
    )

    response = client.post(
        "/groceries/1",
        data={
            "store": "Updated market",
            "purchase_date": "2026-05-21",
            "total_amount": "18.50",
            "notes": "One item removed",
            "item_id": ["1", "2"],
            "item_delete": ["true", "false"],
            "item_name": ["Bananas", "Whole milk"],
            "item_quantity": ["6", "2"],
            "item_unit": ["ct", "gal"],
            "item_price": ["2.49", "9.98"],
            "item_notes": ["", "Family size"],
        },
        follow_redirects=False,
    )

    assert response.status_code == 303

    detail_response = client.get("/groceries/1")
    assert detail_response.status_code == 200
    assert "Updated market" in detail_response.text
    assert "Line Items (1)" in detail_response.text
    assert 'value="Bananas"' not in detail_response.text
    assert "Whole milk" in detail_response.text
    assert "Family size" in detail_response.text


def test_grocery_purchase_detail_can_add_line_item_inline(client: TestClient) -> None:
    client.post(
        "/groceries/",
        data={
            "store": "Test market",
            "purchase_date": "2026-05-20",
            "total_amount": "12.34",
            "notes": "",
            "item_name": ["Bananas"],
            "item_quantity": ["6"],
            "item_unit": ["ct"],
            "item_price": ["2.49"],
            "item_notes": [""],
        },
    )

    response = client.post(
        "/groceries/1",
        data={
            "store": "Test market",
            "purchase_date": "2026-05-20",
            "total_amount": "17.33",
            "notes": "",
            "item_id": ["1", ""],
            "item_delete": ["false", "false"],
            "item_name": ["Bananas", "Milk"],
            "item_quantity": ["6", "1"],
            "item_unit": ["ct", "gal"],
            "item_price": ["2.49", "4.99"],
            "item_notes": ["", "Whole"],
        },
        follow_redirects=False,
    )

    assert response.status_code == 303

    detail_response = client.get("/groceries/1")
    assert detail_response.status_code == 200
    assert "Line Items (2)" in detail_response.text
    assert "Milk" in detail_response.text
    assert "Whole" in detail_response.text


def test_grocery_line_item_can_be_added_to_inventory_once(client: TestClient) -> None:
    client.post(
        "/food/",
        data={
            "name": "Greek yogurt",
            "quantity": "1",
            "unit": "cups",
            "location": "fridge",
            "category": "Dairy",
            "expiration_date": "",
            "notes": "",
        },
    )
    client.post(
        "/groceries/",
        data={
            "store": "Trader Joe's",
            "purchase_date": "2026-05-21",
            "total_amount": "",
            "notes": "",
        },
    )
    client.post(
        "/groceries/1/items",
        data={
            "name": "Greek yogurt",
            "quantity": "2",
            "unit": "cup",
            "price": "",
            "notes": "",
        },
    )

    add_response = client.post(
        "/groceries/1/items/1/add-to-inventory",
        follow_redirects=False,
    )
    assert add_response.status_code == 303

    repeat_response = client.post(
        "/groceries/1/items/1/add-to-inventory",
        follow_redirects=False,
    )
    assert repeat_response.status_code == 303

    inventory_response = client.get("/food/")
    assert inventory_response.status_code == 200
    assert "Greek yogurt" in inventory_response.text
    assert 'value="3"' in inventory_response.text
    assert "Last added from Trader Joe&#39;s purchase on 2026-05-21" in inventory_response.text

    purchase_response = client.get("/groceries/1")
    assert purchase_response.status_code == 200
    assert "Added to inventory" in purchase_response.text
    assert "Add to inventory" not in purchase_response.text


def test_grocery_line_item_merges_gal_with_cups(client: TestClient) -> None:
    client.post(
        "/food/",
        data={
            "name": "Milk",
            "quantity": "1",
            "unit": "gal",
            "location": "fridge",
            "category": "Dairy",
            "expiration_date": "",
            "notes": "",
        },
    )
    client.post(
        "/groceries/",
        data={
            "store": "Costco",
            "purchase_date": "2026-05-21",
            "total_amount": "",
            "notes": "",
        },
    )
    client.post(
        "/groceries/1/items",
        data={
            "name": "Milk",
            "quantity": "4",
            "unit": "cups",
            "price": "",
            "notes": "",
        },
    )

    response = client.post(
        "/groceries/1/items/1/add-to-inventory",
        follow_redirects=False,
    )

    assert response.status_code == 303
    inventory_response = client.get("/food/")
    assert inventory_response.status_code == 200
    assert 'value="1.25"' in inventory_response.text


def test_recipe_can_be_created(client: TestClient) -> None:
    response = client.post(
        "/recipes/",
        data={
            "title": "Test dinner",
            "source": "",
            "cuisine": "",
            "tags": "weeknight",
            "servings": "4",
            "shelf_life_days": "3",
            "calories_per_serving": "",
            "prep_time_minutes": "",
            "cook_time_minutes": "",
            "ingredients": "Rice",
            "instructions": "Cook it.",
            "notes": "",
        },
        follow_redirects=False,
    )

    assert response.status_code == 303

    detail_response = client.get("/recipes/1")
    assert detail_response.status_code == 200
    assert 'name="servings"' in detail_response.text
    assert 'value="4"' in detail_response.text

    update_response = client.post(
        "/recipes/1",
        data={
            "title": "Updated dinner",
            "source": "Family notes",
            "cuisine": "Simple",
            "tags": "weeknight",
            "servings": "2",
            "shelf_life_days": "5",
            "calories_per_serving": "400",
            "prep_time_minutes": "10",
            "cook_time_minutes": "20",
            "ingredients": "Rice\nChicken",
            "instructions": "Cook together.",
            "notes": "Good leftovers.",
        },
        follow_redirects=False,
    )
    assert update_response.status_code == 303

    updated_detail_response = client.get("/recipes/1")
    assert updated_detail_response.status_code == 200
    assert "Updated dinner" in updated_detail_response.text
    assert "Good leftovers." in updated_detail_response.text

    make_response = client.post("/recipes/1/make", follow_redirects=False)
    assert make_response.status_code == 303

    inventory_response = client.get("/food/")
    assert inventory_response.status_code == 200
    assert "Updated dinner" in inventory_response.text
    assert "Prepared meal" in inventory_response.text


def test_recipe_suggestions_render(client: TestClient) -> None:
    client.post(
        "/food/",
        data={
            "name": "Rice",
            "quantity": "1",
            "unit": "bag",
            "location": "pantry",
            "category": "Staple",
            "expiration_date": "",
            "notes": "",
        },
    )
    client.post(
        "/recipes/",
        data={
            "title": "Rice bowl",
            "source": "",
            "cuisine": "",
            "tags": "",
            "servings": "2",
            "shelf_life_days": "",
            "calories_per_serving": "",
            "prep_time_minutes": "",
            "cook_time_minutes": "",
            "ingredients": "Rice\nChicken",
            "instructions": "",
            "notes": "",
        },
    )

    response = client.get("/recipes/suggestions")

    assert response.status_code == 200
    assert "Recipe Suggestions" in response.text
    assert "Rice bowl" in response.text
    assert "Rice" in response.text


def test_restaurant_map_renders_without_google_config(client: TestClient) -> None:
    response = client.get("/restaurants/")

    assert response.status_code == 200
    assert "Restaurants" in response.text
    assert "Google Maps is not configured" in response.text


def test_restaurant_can_be_created_and_updated(client: TestClient) -> None:
    create_response = client.post(
        "/restaurants/",
        json={
            "google_place_id": "test-place-1",
            "name": "Test Bistro",
            "formatted_address": "123 Test St",
            "latitude": 37.77,
            "longitude": -122.42,
            "google_maps_uri": "https://maps.google.com/?cid=test",
            "website_uri": "https://example.test",
            "phone_number": "+1 555-0100",
            "category": "date_night",
        },
    )

    assert create_response.status_code == 201

    duplicate_response = client.post(
        "/restaurants/",
        json={
            "google_place_id": "test-place-1",
            "name": "Duplicate Bistro",
            "latitude": 37.78,
            "longitude": -122.43,
        },
    )
    assert duplicate_response.status_code == 200
    assert duplicate_response.json()["name"] == "Test Bistro"

    update_response = client.post(
        "/restaurants/1",
        data={
            "status": "visited",
            "category": "casual_dates",
            "cuisine": "Italian",
            "tags": "date night, pasta",
            "neighborhood": "Mission",
            "personal_rating": "5",
            "price_level": "$$",
            "notes": "Order the rigatoni.",
        },
        follow_redirects=False,
    )
    assert update_response.status_code == 303

    data_response = client.get("/restaurants/data")
    assert data_response.status_code == 200
    restaurant = data_response.json()["restaurants"][0]
    assert restaurant["name"] == "Test Bistro"
    assert restaurant["status"] == "visited"
    assert restaurant["status_label"] == "Visited"
    assert restaurant["category"] == "casual_dates"
    assert restaurant["category_label"] == "Casual Dates"
    assert restaurant["personal_rating"] == 5
    assert restaurant["notes"] == "Order the rigatoni."


def test_restaurant_legacy_statuses_are_migrated_to_visited(
    client: TestClient,
) -> None:
    from sqlalchemy import text

    from app.db import engine, init_db

    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO restaurants "
                "(google_place_id, name, latitude, longitude, status, created_at, updated_at) "
                "VALUES "
                "('legacy-liked', 'Legacy Liked', 37.77, -122.42, 'LIKED', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP), "
                "('legacy-didnt-like', 'Legacy Didnt Like', 37.78, -122.43, 'DIDNT_LIKE', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP), "
                "('legacy-favorite', 'Legacy Favorite', 37.78, -122.43, 'FAVORITE', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP), "
                "('legacy-skip', 'Legacy Skip', 37.79, -122.44, 'SKIP', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
            )
        )

    init_db()

    response = client.get("/restaurants/data")
    assert response.status_code == 200
    statuses = {
        restaurant["name"]: restaurant["status"]
        for restaurant in response.json()["restaurants"]
    }
    assert statuses["Legacy Liked"] == "visited"
    assert statuses["Legacy Didnt Like"] == "visited"
    assert statuses["Legacy Favorite"] == "visited"
    assert statuses["Legacy Skip"] == "visited"


def test_restaurant_category_column_is_added_to_existing_sqlite_table(
    client: TestClient,
) -> None:
    from sqlalchemy import text

    from app.db import engine, init_db

    with engine.begin() as connection:
        connection.execute(text("ALTER TABLE restaurants DROP COLUMN category"))

    init_db()

    response = client.post(
        "/restaurants/",
        json={
            "google_place_id": "category-place-1",
            "name": "Category Cafe",
            "latitude": 37.77,
            "longitude": -122.42,
            "category": "party_of_one",
        },
    )
    assert response.status_code == 201
    assert response.json()["category"] == "party_of_one"
    assert response.json()["category_label"] == "Party of One"


def test_structured_recipe_ingredients_reduce_inventory(client: TestClient) -> None:
    client.post(
        "/food/",
        data={
            "name": "Lemon",
            "quantity": "4",
            "unit": "ct",
            "location": "fridge",
            "category": "Produce",
            "expiration_date": "",
            "notes": "",
        },
    )
    client.post(
        "/recipes/",
        data={
            "title": "Lemon pasta",
            "source": "",
            "cuisine": "",
            "tags": "",
            "servings": "2",
            "shelf_life_days": "3",
            "calories_per_serving": "",
            "prep_time_minutes": "",
            "cook_time_minutes": "",
            "ingredient_name": ["Lemon"],
            "ingredient_quantity": ["2"],
            "ingredient_unit": ["ct"],
            "ingredient_notes": ["Juiced"],
            "instructions": "",
            "notes": "",
        },
    )

    suggestion_response = client.get("/recipes/suggestions")
    assert suggestion_response.status_code == 200
    assert "2 ct Lemon" in suggestion_response.text
    assert "100% match" in suggestion_response.text

    make_response = client.post("/recipes/1/make", follow_redirects=False)
    assert make_response.status_code == 303

    inventory_response = client.get("/food/")
    assert inventory_response.status_code == 200
    assert 'value="2"' in inventory_response.text
    assert "Lemon pasta" in inventory_response.text
