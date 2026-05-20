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
