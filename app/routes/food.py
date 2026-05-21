from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.food import FoodItem, FoodLocation
from app.routes.pages import templates

router = APIRouter(prefix="/food", tags=["food"])


def _parse_optional_decimal(value: str) -> Decimal | None:
    value = value.strip()
    if not value:
        return None
    try:
        return Decimal(value)
    except InvalidOperation as exc:
        raise ValueError("Quantity must be a number.") from exc


def _parse_optional_date(value: str) -> date | None:
    value = value.strip()
    if not value:
        return None
    return date.fromisoformat(value)


@router.get("/")
def list_food(request: Request, db: Session = Depends(get_db)):
    items = db.scalars(select(FoodItem).order_by(FoodItem.name.asc())).all()
    return templates.TemplateResponse(
        request,
        "food/index.html",
        {
            "active_nav": "food",
            "items": items,
            "locations": list(FoodLocation),
        },
    )


@router.post("/")
def create_food_item(
    name: str = Form(...),
    quantity: str = Form(""),
    unit: str = Form(""),
    location: FoodLocation = Form(FoodLocation.PANTRY),
    category: str = Form(""),
    expiration_date: str = Form(""),
    notes: str = Form(""),
    db: Session = Depends(get_db),
):
    item = FoodItem(
        name=name.strip(),
        quantity=_parse_optional_decimal(quantity),
        unit=unit.strip() or None,
        location=location,
        category=category.strip() or None,
        expiration_date=_parse_optional_date(expiration_date),
        notes=notes.strip() or None,
    )
    db.add(item)
    db.commit()
    return RedirectResponse("/food/", status_code=303)


@router.post("/{item_id}")
def update_food_item(
    item_id: int,
    name: str = Form(...),
    quantity: str = Form(""),
    unit: str = Form(""),
    location: FoodLocation = Form(FoodLocation.PANTRY),
    category: str = Form(""),
    expiration_date: str = Form(""),
    notes: str = Form(""),
    db: Session = Depends(get_db),
):
    item = db.get(FoodItem, item_id)
    if item is None:
        return RedirectResponse("/food/", status_code=303)

    item.name = name.strip()
    item.quantity = _parse_optional_decimal(quantity)
    item.unit = unit.strip() or None
    item.location = location
    item.category = category.strip() or None
    item.expiration_date = _parse_optional_date(expiration_date)
    item.notes = notes.strip() or None
    db.commit()
    return RedirectResponse("/food/", status_code=303)


@router.post("/{item_id}/delete")
def delete_food_item(item_id: int, db: Session = Depends(get_db)):
    item = db.get(FoodItem, item_id)
    if item is not None:
        db.delete(item)
        db.commit()
    return RedirectResponse("/food/", status_code=303)
