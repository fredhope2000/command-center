from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.db import get_db
from app.models.food import GroceryPurchase, GroceryPurchaseItem
from app.routes.pages import templates
from app.services.inventory_reconciliation import add_grocery_item_to_inventory

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


@router.post("/parse-receipt")
def parse_receipt(receipt_image: UploadFile = File(...)):
    try:
        from app.services.receipt_parser.extract import extract_receipt
        from app.services.receipt_parser.upload_validation import validate_uploaded_receipt

        validate_uploaded_receipt(receipt_image)
        preview = extract_receipt(receipt_image)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    return preview


@router.post("/")
async def create_purchase(request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    store = str(form.get("store", ""))
    purchase_date = str(form.get("purchase_date", ""))
    total_amount = str(form.get("total_amount", ""))
    notes = str(form.get("notes", ""))
    purchase = GroceryPurchase(
        store=store.strip(),
        purchase_date=_parse_date(purchase_date),
        total_amount=_parse_optional_decimal(total_amount),
        notes=notes.strip() or None,
    )
    db.add(purchase)
    db.flush()

    item_names = [str(value) for value in form.getlist("item_name")]
    item_quantities = [str(value) for value in form.getlist("item_quantity")]
    item_units = [str(value) for value in form.getlist("item_unit")]
    item_prices = [str(value) for value in form.getlist("item_price")]
    item_notes = [str(value) for value in form.getlist("item_notes")]
    for index, item_name in enumerate(item_names):
        if not item_name.strip():
            continue
        db.add(
            GroceryPurchaseItem(
                purchase_id=purchase.id,
                name=item_name.strip(),
                quantity=_parse_optional_decimal(
                    item_quantities[index] if index < len(item_quantities) else ""
                ),
                unit=item_units[index].strip()
                if index < len(item_units) and item_units[index].strip()
                else None,
                price=_parse_optional_decimal(
                    item_prices[index] if index < len(item_prices) else ""
                ),
                notes=item_notes[index].strip()
                if index < len(item_notes) and item_notes[index].strip()
                else None,
            )
        )

    db.commit()
    return RedirectResponse("/groceries/", status_code=303)


@router.post("/{purchase_id}")
async def update_purchase(
    purchase_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    form = await request.form()
    purchase = db.scalar(
        select(GroceryPurchase)
        .options(selectinload(GroceryPurchase.items))
        .where(GroceryPurchase.id == purchase_id)
    )
    if purchase is None:
        return RedirectResponse("/groceries/", status_code=303)

    purchase.store = str(form.get("store", "")).strip()
    purchase.purchase_date = _parse_date(str(form.get("purchase_date", "")))
    purchase.total_amount = _parse_optional_decimal(str(form.get("total_amount", "")))
    purchase.notes = str(form.get("notes", "")).strip() or None

    item_ids = [str(value) for value in form.getlist("item_id")]
    item_deletes = [str(value) for value in form.getlist("item_delete")]
    item_names = [str(value) for value in form.getlist("item_name")]
    item_quantities = [str(value) for value in form.getlist("item_quantity")]
    item_units = [str(value) for value in form.getlist("item_unit")]
    item_prices = [str(value) for value in form.getlist("item_price")]
    item_notes = [str(value) for value in form.getlist("item_notes")]
    items_by_id = {str(item.id): item for item in purchase.items}
    for index, item_id in enumerate(item_ids):
        item = items_by_id.get(item_id)
        if not item_id:
            if index < len(item_deletes) and item_deletes[index] == "true":
                continue
            name = item_names[index].strip() if index < len(item_names) else ""
            if not name:
                continue
            db.add(
                GroceryPurchaseItem(
                    purchase_id=purchase.id,
                    name=name,
                    quantity=_parse_optional_decimal(
                        item_quantities[index] if index < len(item_quantities) else ""
                    ),
                    unit=item_units[index].strip()
                    if index < len(item_units) and item_units[index].strip()
                    else None,
                    price=_parse_optional_decimal(
                        item_prices[index] if index < len(item_prices) else ""
                    ),
                    notes=item_notes[index].strip()
                    if index < len(item_notes) and item_notes[index].strip()
                    else None,
                )
            )
            continue
        if item is None:
            continue
        if index < len(item_deletes) and item_deletes[index] == "true":
            db.delete(item)
            continue
        item.name = item_names[index].strip() if index < len(item_names) else item.name
        item.quantity = _parse_optional_decimal(
            item_quantities[index] if index < len(item_quantities) else ""
        )
        item.unit = (
            item_units[index].strip()
            if index < len(item_units) and item_units[index].strip()
            else None
        )
        item.price = _parse_optional_decimal(
            item_prices[index] if index < len(item_prices) else ""
        )
        item.notes = (
            item_notes[index].strip()
            if index < len(item_notes) and item_notes[index].strip()
            else None
        )
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


@router.post("/{purchase_id}/items/{item_id}/add-to-inventory")
def add_purchase_item_to_inventory(
    purchase_id: int,
    item_id: int,
    db: Session = Depends(get_db),
):
    purchase = db.get(GroceryPurchase, purchase_id)
    item = db.get(GroceryPurchaseItem, item_id)
    if purchase is None or item is None or item.purchase_id != purchase_id:
        return RedirectResponse(f"/groceries/{purchase_id}", status_code=303)
    if item.inventory_item_id is None:
        add_grocery_item_to_inventory(db, item, purchase)
    return RedirectResponse(f"/groceries/{purchase_id}", status_code=303)


@router.post("/{purchase_id}/delete")
def delete_purchase(purchase_id: int, db: Session = Depends(get_db)):
    purchase = db.get(GroceryPurchase, purchase_id)
    if purchase is not None:
        db.delete(purchase)
        db.commit()
    return RedirectResponse("/groceries/", status_code=303)
