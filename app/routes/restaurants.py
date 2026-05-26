from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.models.food import Restaurant, RestaurantStatus
from app.routes.pages import templates

router = APIRouter(prefix="/restaurants", tags=["restaurants"])


def _clean(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _parse_rating(value: Any) -> int | None:
    text = _clean(value)
    if text is None:
        return None
    rating = int(text)
    if rating < 1 or rating > 5:
        raise ValueError("Rating must be between 1 and 5.")
    return rating


def _restaurant_payload(restaurant: Restaurant) -> dict[str, Any]:
    return {
        "id": restaurant.id,
        "google_place_id": restaurant.google_place_id,
        "name": restaurant.name,
        "formatted_address": restaurant.formatted_address,
        "latitude": restaurant.latitude,
        "longitude": restaurant.longitude,
        "google_maps_uri": restaurant.google_maps_uri,
        "website_uri": restaurant.website_uri,
        "phone_number": restaurant.phone_number,
        "status": restaurant.status.value,
        "status_label": _status_label(restaurant.status.value),
        "cuisine": restaurant.cuisine,
        "tags": restaurant.tags,
        "neighborhood": restaurant.neighborhood,
        "personal_rating": restaurant.personal_rating,
        "price_level": restaurant.price_level,
        "notes": restaurant.notes,
    }


def _wants_json(request: Request) -> bool:
    return "application/json" in request.headers.get("accept", "")


def _status_options() -> list[dict[str, str]]:
    return [
        {"value": status.value, "label": _status_label(status.value)}
        for status in RestaurantStatus
    ]


def _status_label(status: str) -> str:
    return {
        RestaurantStatus.WANT_TO_TRY.value: "Want To Try",
        RestaurantStatus.VISITED.value: "Visited",
        RestaurantStatus.PERMANENTLY_CLOSED.value: "Permanently Closed",
    }.get(status, status.replace("_", " ").title())


@router.get("/")
def restaurant_map(request: Request, db: Session = Depends(get_db)):
    restaurants = db.scalars(select(Restaurant).order_by(Restaurant.name.asc())).all()
    return templates.TemplateResponse(
        request,
        "restaurants/index.html",
        {
            "active_nav": "restaurants",
            "google_maps_api_key": settings.google_maps_api_key,
            "google_maps_map_id": settings.google_maps_map_id,
            "restaurants": restaurants,
            "statuses": _status_options(),
        },
    )


@router.get("/data")
def restaurant_data(db: Session = Depends(get_db)):
    restaurants = db.scalars(select(Restaurant).order_by(Restaurant.name.asc())).all()
    return {
        "restaurants": [_restaurant_payload(restaurant) for restaurant in restaurants],
        "statuses": _status_options(),
    }


@router.post("/")
async def create_restaurant(request: Request, db: Session = Depends(get_db)):
    payload = await request.json()
    place_id = _clean(payload.get("google_place_id") or payload.get("place_id"))
    name = _clean(payload.get("name"))
    latitude = payload.get("latitude")
    longitude = payload.get("longitude")

    if not place_id or not name or latitude is None or longitude is None:
        return JSONResponse(
            {"error": "Google place ID, name, latitude, and longitude are required."},
            status_code=400,
        )

    existing = db.scalar(
        select(Restaurant).where(Restaurant.google_place_id == place_id)
    )
    if existing is not None:
        return JSONResponse(_restaurant_payload(existing), status_code=200)

    restaurant = Restaurant(
        google_place_id=place_id,
        name=name,
        formatted_address=_clean(payload.get("formatted_address")),
        latitude=float(latitude),
        longitude=float(longitude),
        google_maps_uri=_clean(payload.get("google_maps_uri")),
        website_uri=_clean(payload.get("website_uri")),
        phone_number=_clean(payload.get("phone_number")),
        status=RestaurantStatus(_clean(payload.get("status")) or "want_to_try"),
        cuisine=_clean(payload.get("cuisine")),
        tags=_clean(payload.get("tags")),
        neighborhood=_clean(payload.get("neighborhood")),
        personal_rating=_parse_rating(payload.get("personal_rating")),
        price_level=_clean(payload.get("price_level")),
        notes=_clean(payload.get("notes")),
    )
    db.add(restaurant)
    db.commit()
    db.refresh(restaurant)
    return JSONResponse(_restaurant_payload(restaurant), status_code=201)


@router.post("/{restaurant_id}")
def update_restaurant(
    request: Request,
    restaurant_id: int,
    status: RestaurantStatus = Form(RestaurantStatus.WANT_TO_TRY),
    cuisine: str = Form(""),
    tags: str = Form(""),
    neighborhood: str = Form(""),
    personal_rating: str = Form(""),
    price_level: str = Form(""),
    notes: str = Form(""),
    db: Session = Depends(get_db),
):
    restaurant = db.get(Restaurant, restaurant_id)
    if restaurant is None:
        if _wants_json(request):
            return JSONResponse({"error": "Restaurant not found."}, status_code=404)
        return RedirectResponse("/restaurants/", status_code=303)

    restaurant.status = status
    restaurant.cuisine = _clean(cuisine)
    restaurant.tags = _clean(tags)
    restaurant.neighborhood = _clean(neighborhood)
    restaurant.personal_rating = _parse_rating(personal_rating)
    restaurant.price_level = _clean(price_level)
    restaurant.notes = _clean(notes)
    db.commit()
    db.refresh(restaurant)
    if _wants_json(request):
        return JSONResponse(_restaurant_payload(restaurant))
    return RedirectResponse("/restaurants/", status_code=303)


@router.post("/{restaurant_id}/delete")
def delete_restaurant(restaurant_id: int, db: Session = Depends(get_db)):
    restaurant = db.get(Restaurant, restaurant_id)
    if restaurant is not None:
        db.delete(restaurant)
        db.commit()
    return RedirectResponse("/restaurants/", status_code=303)
