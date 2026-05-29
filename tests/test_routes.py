from __future__ import annotations

import importlib
import sys
from collections.abc import Iterator

import bcrypt
from fastapi.testclient import TestClient
import pytest


def _reload_app() -> object:
    for name in list(sys.modules):
        if name == "app" or name.startswith("app."):
            sys.modules.pop(name)
    return importlib.import_module("app.main")


def _reload_config() -> object:
    for name in list(sys.modules):
        if name == "app.config":
            sys.modules.pop(name)
    return importlib.import_module("app.config")


@pytest.fixture()
def client(tmp_path, monkeypatch) -> Iterator[TestClient]:
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'test.sqlite'}")
    monkeypatch.setenv("COMMAND_CENTER_AUTH_ENABLED", "false")
    monkeypatch.delenv("GOOGLE_MAPS_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_MAPS_MAP_ID", raising=False)
    monkeypatch.delenv("RESTAURANT_PHOTOS_S3_BUCKET", raising=False)
    monkeypatch.delenv("RESTAURANT_PHOTOS_BASE_URL", raising=False)

    main = _reload_app()
    with TestClient(main.app) as test_client:
        yield test_client


@pytest.fixture()
def auth_client(tmp_path, monkeypatch) -> Iterator[TestClient]:
    password_hash = bcrypt.hashpw(b"house-password", bcrypt.gensalt()).decode("utf-8")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'test.sqlite'}")
    monkeypatch.setenv("COMMAND_CENTER_AUTH_ENABLED", "true")
    monkeypatch.setenv("COMMAND_CENTER_PASSWORD_HASH", password_hash)
    monkeypatch.setenv("COMMAND_CENTER_AUTH_SECRET", "test-cookie-signing-secret")
    monkeypatch.delenv("GOOGLE_MAPS_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_MAPS_MAP_ID", raising=False)
    monkeypatch.delenv("RESTAURANT_PHOTOS_S3_BUCKET", raising=False)
    monkeypatch.delenv("RESTAURANT_PHOTOS_BASE_URL", raising=False)

    main = _reload_app()
    with TestClient(main.app) as test_client:
        yield test_client


def test_logged_out_user_gets_login_page_instead_of_app_html(
    auth_client: TestClient,
) -> None:
    response = auth_client.get("/food/", follow_redirects=True)

    assert response.status_code == 200
    assert "Command Center" in response.text
    assert 'name="password"' in response.text
    assert "Food Inventory" not in response.text


def test_login_sets_cookie_and_allows_app_access(auth_client: TestClient) -> None:
    login_response = auth_client.post(
        "/login",
        data={"password": "house-password", "next": "/food/"},
        follow_redirects=False,
    )

    assert login_response.status_code == 303
    assert login_response.headers["location"] == "/food/"
    assert "command_center_auth=" in login_response.headers["set-cookie"]
    assert "Max-Age=7776000" in login_response.headers["set-cookie"]

    page_response = auth_client.get("/food/")
    assert page_response.status_code == 200
    assert "Food Inventory" in page_response.text


def test_logout_clears_cookie_and_requires_login(auth_client: TestClient) -> None:
    auth_client.post(
        "/login",
        data={"password": "house-password", "next": "/food/"},
    )

    logout_response = auth_client.post("/logout", follow_redirects=False)

    assert logout_response.status_code == 303
    assert logout_response.headers["location"] == "/login"
    assert "command_center_auth=" in logout_response.headers["set-cookie"]

    page_response = auth_client.get("/food/", follow_redirects=False)
    assert page_response.status_code == 303
    assert page_response.headers["location"].startswith("/login")


def test_restaurant_photo_storage_defaults_follow_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("RESTAURANT_PHOTOS_S3_BUCKET", raising=False)
    monkeypatch.delenv("RESTAURANT_PHOTOS_BASE_URL", raising=False)
    monkeypatch.delenv("RESTAURANT_PHOTOS_S3_PREFIX", raising=False)

    monkeypatch.setenv("APP_ENV", "development")
    config = _reload_config()
    assert config.settings.restaurant_photos_s3_bucket == "fredhopedotcom"
    assert config.settings.restaurant_photos_base_url == "https://fredhope.com"
    assert config.settings.restaurant_photos_s3_prefix == "ec2/command-center-dev"

    monkeypatch.setenv("APP_ENV", "production")
    config = _reload_config()
    assert config.settings.restaurant_photos_s3_bucket == "fredhopedotcom"
    assert config.settings.restaurant_photos_base_url == "https://fredhope.com"
    assert config.settings.restaurant_photos_s3_prefix == "ec2/command-center"


def test_restaurant_ai_is_enabled_only_in_production_with_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    config = _reload_config()
    assert config.settings.restaurant_ai_enabled is False

    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    config = _reload_config()
    assert config.settings.restaurant_ai_enabled is False

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    config = _reload_config()
    assert config.settings.restaurant_ai_enabled is True


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
    assert "data-restaurant-rating-filter" in response.text
    assert "data-restaurant-menu-search" in response.text
    assert "0 of 0 items shown" in response.text
    assert "0 saved" not in response.text


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
            "menu_url": "https://example.test/menu",
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
            "menu_url": "https://example.test/current-menu",
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
    assert restaurant["menu_url"] == "https://example.test/current-menu"
    assert restaurant["notes"] == "Order the rigatoni."
    assert restaurant["photos"] == []

    custom_name_response = client.post(
        "/restaurants/1",
        data={
            "status": "visited",
            "category": "casual_dates",
            "custom_name": "The Rigatoni Place",
            "personal_rating": "5",
        },
        headers={"accept": "application/json"},
    )
    assert custom_name_response.status_code == 200
    assert custom_name_response.json()["name"] == "The Rigatoni Place"
    assert custom_name_response.json()["google_name"] == "Test Bistro"
    assert custom_name_response.json()["custom_name"] == "The Rigatoni Place"

    clear_name_response = client.post(
        "/restaurants/1",
        data={
            "status": "visited",
            "category": "casual_dates",
            "custom_name": "",
            "personal_rating": "5",
        },
        headers={"accept": "application/json"},
    )
    assert clear_name_response.status_code == 200
    assert clear_name_response.json()["name"] == "Test Bistro"
    assert clear_name_response.json()["google_name"] == "Test Bistro"
    assert clear_name_response.json()["custom_name"] is None


def test_restaurant_menu_refresh_uses_dev_mock_cache(client: TestClient) -> None:
    create_response = client.post(
        "/restaurants/",
        json={
            "google_place_id": "menu-place-1",
            "name": "Menu Cafe",
            "latitude": 37.77,
            "longitude": -122.42,
            "website_uri": "https://example.test",
            "menu_url": "https://example.test/direct-menu",
            "cuisine": "Noodles",
            "tags": "smoky, casual",
        },
    )
    assert create_response.status_code == 201
    assert create_response.json()["menu_cache"] is None

    refresh_response = client.post("/restaurants/1/menu/refresh")

    assert refresh_response.status_code == 200
    restaurant = refresh_response.json()["restaurant"]
    assert restaurant["menu_cache"]["status"] == "mocked"
    assert restaurant["menu_cache"]["source_url"] == "https://example.test/direct-menu"
    assert restaurant["menu_cache"]["item_count"] == 2
    assert restaurant["menu_cache"]["summary"] == (
        "Development mock menu generated without AI."
    )

    data_response = client.get("/restaurants/data")
    assert data_response.json()["restaurants"][0]["menu_cache"]["status"] == "mocked"

    menu_response = client.get("/restaurants/1/menu")
    assert menu_response.status_code == 200
    assert menu_response.json()["source_url"] == "https://example.test/direct-menu"
    assert "smoky grilled vegetables" in menu_response.json()["extracted_text"]
    assert len(menu_response.json()["structured_json"]["items"]) == 2


def test_restaurant_menu_search_uses_cached_menu_data(client: TestClient) -> None:
    client.post(
        "/restaurants/",
        json={
            "google_place_id": "search-menu-place-1",
            "name": "Search Menu Cafe",
            "latitude": 37.77,
            "longitude": -122.42,
        },
    )
    client.post("/restaurants/1/menu/refresh")

    response = client.post("/restaurants/menu/search", json={"query": "smoky"})

    assert response.status_code == 200
    results = response.json()["results"]
    assert results[0]["restaurant_id"] == 1
    assert results[0]["name"] == "Search Menu Cafe"
    assert "smoky" in results[0]["matched_terms"]


def test_restaurant_photos_can_be_uploaded_and_removed(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from io import BytesIO

    from PIL import Image

    from app.routes import restaurants as restaurant_routes

    uploaded_keys: list[str] = []
    deleted_keys: list[str] = []

    def fake_upload(upload_file, restaurant_id: int) -> dict[str, str]:
        uploaded_keys.append(f"restaurants/{restaurant_id}/photo.jpg")
        return {
            "storage_key": uploaded_keys[-1],
            "url": f"https://cdn.example.test/{uploaded_keys[-1]}",
            "content_type": "image/jpeg",
        }

    monkeypatch.setattr(restaurant_routes, "upload_restaurant_photo", fake_upload)
    monkeypatch.setattr(
        restaurant_routes, "delete_restaurant_photo", deleted_keys.append
    )

    create_response = client.post(
        "/restaurants/",
        json={
            "google_place_id": "photo-place-1",
            "name": "Photo Cafe",
            "latitude": 37.77,
            "longitude": -122.42,
        },
    )
    assert create_response.status_code == 201

    image_buffer = BytesIO()
    Image.new("RGB", (4, 4), color="red").save(image_buffer, format="PNG")
    image_buffer.seek(0)

    upload_response = client.post(
        "/restaurants/1/photos",
        files={"photo": ("dish.png", image_buffer, "image/png")},
    )
    assert upload_response.status_code == 201
    assert upload_response.json()["photo"]["url"] == (
        "https://cdn.example.test/restaurants/1/photo.jpg"
    )
    assert upload_response.json()["restaurant"]["photos"][0]["original_filename"] == (
        "dish.png"
    )

    data_response = client.get("/restaurants/data")
    assert data_response.json()["restaurants"][0]["photos"][0]["url"] == (
        "https://cdn.example.test/restaurants/1/photo.jpg"
    )

    delete_response = client.post("/restaurants/1/photos/1/delete")
    assert delete_response.status_code == 200
    assert delete_response.json()["deleted"] == 1
    assert delete_response.json()["restaurant"]["photos"] == []
    assert deleted_keys == ["restaurants/1/photo.jpg"]


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


def test_restaurant_custom_name_column_is_added_to_existing_sqlite_table(
    client: TestClient,
) -> None:
    from sqlalchemy import text

    from app.db import engine, init_db

    with engine.begin() as connection:
        connection.execute(text("ALTER TABLE restaurants DROP COLUMN custom_name"))

    init_db()

    response = client.post(
        "/restaurants/",
        json={
            "google_place_id": "custom-name-place-1",
            "name": "Maps Cafe",
            "custom_name": "House Cafe",
            "latitude": 37.77,
            "longitude": -122.42,
        },
    )
    assert response.status_code == 201
    assert response.json()["name"] == "House Cafe"
    assert response.json()["google_name"] == "Maps Cafe"
    assert response.json()["custom_name"] == "House Cafe"


def test_restaurant_menu_url_column_is_added_to_existing_sqlite_table(
    client: TestClient,
) -> None:
    from sqlalchemy import text

    from app.db import engine, init_db

    with engine.begin() as connection:
        connection.execute(text("ALTER TABLE restaurants DROP COLUMN menu_url"))

    init_db()

    response = client.post(
        "/restaurants/",
        json={
            "google_place_id": "menu-url-place-1",
            "name": "Menu URL Cafe",
            "menu_url": "https://example.test/menu.pdf",
            "latitude": 37.77,
            "longitude": -122.42,
        },
    )
    assert response.status_code == 201
    assert response.json()["menu_url"] == "https://example.test/menu.pdf"


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
