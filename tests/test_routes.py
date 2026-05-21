from __future__ import annotations

import importlib
import sys
from collections.abc import Iterator

from fastapi.testclient import TestClient
import pytest


@pytest.fixture()
def client(tmp_path, monkeypatch) -> Iterator[TestClient]:
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'test.sqlite'}")
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


def test_grocery_purchase_can_be_created(client: TestClient) -> None:
    response = client.post(
        "/groceries/",
        data={
            "store": "Test market",
            "purchase_date": "2026-05-20",
            "total_amount": "12.34",
            "notes": "",
        },
        follow_redirects=False,
    )

    assert response.status_code == 303


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


def test_recipe_can_be_created(client: TestClient) -> None:
    response = client.post(
        "/recipes/",
        data={
            "title": "Test dinner",
            "source": "",
            "cuisine": "",
            "tags": "weeknight",
            "calories": "",
            "prep_time_minutes": "",
            "cook_time_minutes": "",
            "ingredients": "Rice",
            "instructions": "Cook it.",
            "notes": "",
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
