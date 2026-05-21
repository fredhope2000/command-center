from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.db import get_db
from app.models.food import GroceryPurchase, GroceryPurchaseItem
from app.routes.pages import templates

router = APIRouter(prefix="/groceries", tags=["groceries"])


def _parse_optional_decimal(value: str) -> Decimal | None:
    value = value.strip()
    if not value:
        return None
    try:
        return Decimal(value)
    except InvalidOperation as exc:
        raise ValueError("Amount must be a number.") from exc


def _parse_date(value: str) -> date:
    value = value.strip()
    if not value:
        return date.today()
    return date.fromisoformat(value)


@router.get("/")
def list_purchases(request: Request, db: Session = Depends(get_db)):
    purchases = db.scalars(
        select(GroceryPurchase)
        .options(selectinload(GroceryPurchase.items))
        .order_by(GroceryPurchase.purchase_date.desc(), GroceryPurchase.created_at.desc())
    ).all()
    return templates.TemplateResponse(
        request,
        "groceries/index.html",
        {"active_nav": "groceries", "purchases": purchases},
    )


@router.post("/")
def create_purchase(
    store: str = Form(...),
    purchase_date: str = Form(""),
    total_amount: str = Form(""),
    notes: str = Form(""),
    db: Session = Depends(get_db),
):
    purchase = GroceryPurchase(
        store=store.strip(),
        purchase_date=_parse_date(purchase_date),
        total_amount=_parse_optional_decimal(total_amount),
        notes=notes.strip() or None,
    )
    db.add(purchase)
    db.commit()
    return RedirectResponse("/groceries/", status_code=303)


@router.post("/{purchase_id}")
def update_purchase(
    purchase_id: int,
    store: str = Form(...),
    purchase_date: str = Form(""),
    total_amount: str = Form(""),
    notes: str = Form(""),
    db: Session = Depends(get_db),
):
    purchase = db.get(GroceryPurchase, purchase_id)
    if purchase is None:
        return RedirectResponse("/groceries/", status_code=303)

    purchase.store = store.strip()
    purchase.purchase_date = _parse_date(purchase_date)
    purchase.total_amount = _parse_optional_decimal(total_amount)
    purchase.notes = notes.strip() or None
    db.commit()
    return RedirectResponse(f"/groceries/{purchase.id}", status_code=303)


@router.get("/{purchase_id}")
def purchase_detail(purchase_id: int, request: Request, db: Session = Depends(get_db)):
    purchase = db.scalar(
        select(GroceryPurchase)
        .options(selectinload(GroceryPurchase.items))
        .where(GroceryPurchase.id == purchase_id)
    )
    if purchase is None:
        return RedirectResponse("/groceries/", status_code=303)
    return templates.TemplateResponse(
        request,
        "groceries/detail.html",
        {"active_nav": "groceries", "purchase": purchase},
    )


@router.post("/{purchase_id}/items")
def add_purchase_item(
    purchase_id: int,
    name: str = Form(...),
    quantity: str = Form(""),
    unit: str = Form(""),
    price: str = Form(""),
    notes: str = Form(""),
    db: Session = Depends(get_db),
):
    purchase = db.get(GroceryPurchase, purchase_id)
    if purchase is None:
        return RedirectResponse("/groceries/", status_code=303)
    item = GroceryPurchaseItem(
        purchase_id=purchase.id,
        name=name.strip(),
        quantity=_parse_optional_decimal(quantity),
        unit=unit.strip() or None,
        price=_parse_optional_decimal(price),
        notes=notes.strip() or None,
    )
    db.add(item)
    db.commit()
    return RedirectResponse(f"/groceries/{purchase.id}", status_code=303)


@router.post("/{purchase_id}/items/{item_id}")
def update_purchase_item(
    purchase_id: int,
    item_id: int,
    name: str = Form(...),
    quantity: str = Form(""),
    unit: str = Form(""),
    price: str = Form(""),
    notes: str = Form(""),
    db: Session = Depends(get_db),
):
    item = db.get(GroceryPurchaseItem, item_id)
    if item is None or item.purchase_id != purchase_id:
        return RedirectResponse(f"/groceries/{purchase_id}", status_code=303)

    item.name = name.strip()
    item.quantity = _parse_optional_decimal(quantity)
    item.unit = unit.strip() or None
    item.price = _parse_optional_decimal(price)
    item.notes = notes.strip() or None
    db.commit()
    return RedirectResponse(f"/groceries/{purchase_id}", status_code=303)


@router.post("/{purchase_id}/items/{item_id}/delete")
def delete_purchase_item(
    purchase_id: int,
    item_id: int,
    db: Session = Depends(get_db),
):
    item = db.get(GroceryPurchaseItem, item_id)
    if item is not None and item.purchase_id == purchase_id:
        db.delete(item)
        db.commit()
    return RedirectResponse(f"/groceries/{purchase_id}", status_code=303)


@router.post("/{purchase_id}/delete")
def delete_purchase(purchase_id: int, db: Session = Depends(get_db)):
    purchase = db.get(GroceryPurchase, purchase_id)
    if purchase is not None:
        db.delete(purchase)
        db.commit()
    return RedirectResponse("/groceries/", status_code=303)
