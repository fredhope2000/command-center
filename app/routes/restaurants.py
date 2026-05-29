from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.models.food import (
    Restaurant,
    RestaurantCategory,
    RestaurantPhoto,
    RestaurantStatus,
)
from app.routes.pages import templates
from app.services.restaurant_photos import (
    delete_restaurant_photo,
    upload_restaurant_photo,
)
from app.services.restaurant_menus import (
    apply_menu_result,
    import_menu_text_for_restaurant,
    menu_cache_is_pending,
    menu_cache_pending_is_stale,
    menu_cache_payload,
    queue_menu_ai_structure,
    refresh_menu_for_restaurant,
    search_restaurant_menus,
)

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
    display_name = restaurant.custom_name or restaurant.name
    return {
        "id": restaurant.id,
        "google_place_id": restaurant.google_place_id,
        "name": display_name,
        "google_name": restaurant.name,
        "custom_name": restaurant.custom_name,
        "formatted_address": restaurant.formatted_address,
        "latitude": restaurant.latitude,
        "longitude": restaurant.longitude,
        "google_maps_uri": restaurant.google_maps_uri,
        "website_uri": restaurant.website_uri,
        "menu_url": restaurant.menu_url,
        "phone_number": restaurant.phone_number,
        "status": restaurant.status.value,
        "status_label": _status_label(restaurant.status.value),
        "category": restaurant.category.value if restaurant.category else None,
        "category_label": _category_label(restaurant.category.value)
        if restaurant.category
        else None,
        "cuisine": restaurant.cuisine,
        "tags": restaurant.tags,
        "neighborhood": restaurant.neighborhood,
        "personal_rating": restaurant.personal_rating,
        "price_level": restaurant.price_level,
        "notes": restaurant.notes,
        "menu_cache": menu_cache_payload(restaurant),
        "photos": [_restaurant_photo_payload(photo) for photo in restaurant.photos],
    }


def _restaurant_photo_payload(photo: RestaurantPhoto) -> dict[str, Any]:
    return {
        "id": photo.id,
        "url": photo.url,
        "original_filename": photo.original_filename,
        "content_type": photo.content_type,
        "created_at": photo.created_at.isoformat(),
    }


def _wants_json(request: Request) -> bool:
    return "application/json" in request.headers.get("accept", "")


def _status_options() -> list[dict[str, str]]:
    return [
        {"value": status.value, "label": _status_label(status.value)}
        for status in RestaurantStatus
    ]


def _category_options() -> list[dict[str, str]]:
    return [
        {"value": category.value, "label": _category_label(category.value)}
        for category in RestaurantCategory
    ]


def _status_label(status: str) -> str:
    return {
        RestaurantStatus.WANT_TO_TRY.value: "Want To Try",
        RestaurantStatus.VISITED.value: "Visited",
        RestaurantStatus.PERMANENTLY_CLOSED.value: "Permanently Closed",
    }.get(status, status.replace("_", " ").title())


def _category_label(category: str) -> str:
    return {
        RestaurantCategory.PARTY_OF_ONE.value: "Party of One",
        RestaurantCategory.DATE_NIGHT.value: "Date Night",
        RestaurantCategory.CASUAL_DATES.value: "Casual Dates",
        RestaurantCategory.LINDA_ONLY.value: "Linda Only",
        RestaurantCategory.DESSERT.value: "Dessert",
    }.get(category, category.replace("_", " ").title())


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
            "categories": _category_options(),
        },
    )


@router.get("/data")
def restaurant_data(db: Session = Depends(get_db)):
    restaurants = db.scalars(select(Restaurant).order_by(Restaurant.name.asc())).all()
    return {
        "restaurants": [_restaurant_payload(restaurant) for restaurant in restaurants],
        "statuses": _status_options(),
        "categories": _category_options(),
    }


@router.post("/menu/search")
async def restaurant_menu_search(request: Request, db: Session = Depends(get_db)):
    payload = await request.json()
    query = _clean(payload.get("query"))
    if query is None:
        return JSONResponse({"error": "Search query is required."}, status_code=400)

    restaurants = db.scalars(select(Restaurant).order_by(Restaurant.name.asc())).all()
    return {"results": search_restaurant_menus(restaurants, query)}


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
        menu_url=_clean(payload.get("menu_url")),
        phone_number=_clean(payload.get("phone_number")),
        custom_name=_clean(payload.get("custom_name")),
        status=RestaurantStatus(_clean(payload.get("status")) or "want_to_try"),
        category=RestaurantCategory(_clean(payload.get("category")))
        if _clean(payload.get("category"))
        else None,
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
    category: str = Form(""),
    cuisine: str = Form(""),
    tags: str = Form(""),
    neighborhood: str = Form(""),
    custom_name: str = Form(""),
    personal_rating: str = Form(""),
    price_level: str = Form(""),
    menu_url: str = Form(""),
    notes: str = Form(""),
    db: Session = Depends(get_db),
):
    restaurant = db.get(Restaurant, restaurant_id)
    if restaurant is None:
        if _wants_json(request):
            return JSONResponse({"error": "Restaurant not found."}, status_code=404)
        return RedirectResponse("/restaurants/", status_code=303)

    restaurant.status = status
    restaurant.category = (
        RestaurantCategory(category) if _clean(category) is not None else None
    )
    restaurant.cuisine = _clean(cuisine)
    restaurant.tags = _clean(tags)
    restaurant.neighborhood = _clean(neighborhood)
    restaurant.custom_name = _clean(custom_name)
    restaurant.personal_rating = _parse_rating(personal_rating)
    restaurant.price_level = _clean(price_level)
    restaurant.menu_url = _clean(menu_url)
    restaurant.notes = _clean(notes)
    db.commit()
    db.refresh(restaurant)
    if _wants_json(request):
        return JSONResponse(_restaurant_payload(restaurant))
    return RedirectResponse("/restaurants/", status_code=303)


@router.post("/{restaurant_id}/delete")
def delete_restaurant(
    request: Request,
    restaurant_id: int,
    db: Session = Depends(get_db),
):
    restaurant = db.get(Restaurant, restaurant_id)
    if restaurant is not None:
        photo_keys = [photo.storage_key for photo in restaurant.photos]
        db.delete(restaurant)
        db.commit()
        for storage_key in photo_keys:
            delete_restaurant_photo(storage_key)
    if _wants_json(request):
        return JSONResponse({"deleted": restaurant_id})
    return RedirectResponse("/restaurants/", status_code=303)


@router.post("/{restaurant_id}/photos")
def add_restaurant_photo(
    restaurant_id: int,
    photo: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    restaurant = db.get(Restaurant, restaurant_id)
    if restaurant is None:
        return JSONResponse({"error": "Restaurant not found."}, status_code=404)
    if menu_cache_is_pending(restaurant) and not menu_cache_pending_is_stale(restaurant):
        return JSONResponse(
            {"error": "Menu parsing is already in progress."},
            status_code=409,
        )

    try:
        uploaded = upload_restaurant_photo(photo, restaurant_id)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)

    restaurant_photo = RestaurantPhoto(
        restaurant_id=restaurant.id,
        storage_key=uploaded["storage_key"],
        url=uploaded["url"],
        original_filename=_clean(photo.filename),
        content_type=uploaded["content_type"],
    )
    db.add(restaurant_photo)
    db.commit()
    db.refresh(restaurant_photo)
    db.refresh(restaurant)

    return JSONResponse(
        {
            "photo": _restaurant_photo_payload(restaurant_photo),
            "restaurant": _restaurant_payload(restaurant),
        },
        status_code=201,
    )


@router.post("/{restaurant_id}/photos/{photo_id}/delete")
def remove_restaurant_photo(
    restaurant_id: int,
    photo_id: int,
    db: Session = Depends(get_db),
):
    photo = db.get(RestaurantPhoto, photo_id)
    if photo is None or photo.restaurant_id != restaurant_id:
        return JSONResponse({"error": "Photo not found."}, status_code=404)

    storage_key = photo.storage_key
    db.delete(photo)
    db.commit()
    delete_restaurant_photo(storage_key)

    restaurant = db.get(Restaurant, restaurant_id)
    return JSONResponse(
        {
            "deleted": photo_id,
            "restaurant": _restaurant_payload(restaurant) if restaurant else None,
        }
    )


@router.post("/{restaurant_id}/menu/refresh")
def refresh_restaurant_menu(
    restaurant_id: int,
    db: Session = Depends(get_db),
):
    restaurant = db.get(Restaurant, restaurant_id)
    if restaurant is None:
        return JSONResponse({"error": "Restaurant not found."}, status_code=404)

    try:
        result = refresh_menu_for_restaurant(restaurant)
    except (RuntimeError, ValueError) as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)

    apply_menu_result(restaurant, result)
    db.add(restaurant)
    db.commit()
    db.refresh(restaurant)
    if result.status == "fetch_pending":
        queue_menu_ai_structure(restaurant.id, "fetched")
    return JSONResponse({"restaurant": _restaurant_payload(restaurant)})


@router.get("/{restaurant_id}/menu")
def restaurant_menu_data(
    restaurant_id: int,
    db: Session = Depends(get_db),
):
    restaurant = db.get(Restaurant, restaurant_id)
    if restaurant is None:
        return JSONResponse({"error": "Restaurant not found."}, status_code=404)
    cache = restaurant.menu_cache
    if cache is None:
        return JSONResponse({"error": "No menu cache found."}, status_code=404)
    return {
        "restaurant_id": restaurant.id,
        "restaurant_name": restaurant.custom_name or restaurant.name,
        "status": cache.last_success_status or cache.status,
        "source_url": cache.last_success_source_url or cache.source_url,
        "fetched_at": (
            cache.last_success_at.isoformat()
            if cache.last_success_at
            else cache.fetched_at.isoformat()
            if cache.fetched_at
            else None
        ),
        "latest_status": cache.status,
        "error_message": cache.error_message,
        "extracted_text": cache.extracted_text or "",
        "structured_json": cache.structured_json or {},
    }


@router.post("/{restaurant_id}/menu/import")
async def import_restaurant_menu(
    request: Request,
    restaurant_id: int,
    db: Session = Depends(get_db),
):
    restaurant = db.get(Restaurant, restaurant_id)
    if restaurant is None:
        return JSONResponse({"error": "Restaurant not found."}, status_code=404)
    if menu_cache_is_pending(restaurant) and not menu_cache_pending_is_stale(restaurant):
        return JSONResponse(
            {"error": "Menu parsing is already in progress."},
            status_code=409,
        )

    payload = await request.json()
    extracted_text = _clean(payload.get("extracted_text"))
    if extracted_text is None:
        return JSONResponse({"error": "Menu text is required."}, status_code=400)

    result = import_menu_text_for_restaurant(
        restaurant,
        source_url=_clean(payload.get("source_url")) or restaurant.menu_url,
        extracted_text=extracted_text,
    )
    apply_menu_result(restaurant, result)
    if result.source_url:
        restaurant.menu_url = result.source_url
    db.add(restaurant)
    db.commit()
    db.refresh(restaurant)
    if result.status == "import_pending":
        queue_menu_ai_structure(restaurant.id, "imported")
    return JSONResponse({"restaurant": _restaurant_payload(restaurant)})


@router.post("/{restaurant_id}/menu/error/clear")
def clear_restaurant_menu_error(
    restaurant_id: int,
    db: Session = Depends(get_db),
):
    restaurant = db.get(Restaurant, restaurant_id)
    if restaurant is None:
        return JSONResponse({"error": "Restaurant not found."}, status_code=404)
    cache = restaurant.menu_cache
    if cache is None:
        return JSONResponse({"error": "No menu cache found."}, status_code=404)

    if cache.last_success_status:
        cache.status = cache.last_success_status
        cache.source_url = cache.last_success_source_url or cache.source_url
        cache.fetched_at = cache.last_success_at or cache.fetched_at
    elif cache.extracted_text:
        cache.status = "cached"
    cache.error_message = None
    db.commit()
    db.refresh(restaurant)
    return JSONResponse({"restaurant": _restaurant_payload(restaurant)})
