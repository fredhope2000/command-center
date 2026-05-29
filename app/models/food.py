from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum

from sqlalchemy import (
    Date,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    JSON,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class FoodLocation(StrEnum):
    FRIDGE = "fridge"
    FREEZER = "freezer"
    PANTRY = "pantry"
    OTHER = "other"


class FoodItem(Base):
    __tablename__ = "food_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    quantity: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    unit: Mapped[str | None] = mapped_column(String(40), nullable=True)
    location: Mapped[FoodLocation] = mapped_column(
        Enum(FoodLocation), nullable=False, default=FoodLocation.PANTRY
    )
    category: Mapped[str | None] = mapped_column(String(80), nullable=True)
    expiration_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )


class GroceryPurchase(Base):
    __tablename__ = "grocery_purchases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    store: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    purchase_date: Mapped[date] = mapped_column(Date, nullable=False, default=date.today)
    total_amount: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    items: Mapped[list["GroceryPurchaseItem"]] = relationship(
        back_populates="purchase", cascade="all, delete-orphan"
    )


class GroceryPurchaseItem(Base):
    __tablename__ = "grocery_purchase_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    purchase_id: Mapped[int] = mapped_column(
        ForeignKey("grocery_purchases.id"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    quantity: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    unit: Mapped[str | None] = mapped_column(String(40), nullable=True)
    price: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    inventory_item_id: Mapped[int | None] = mapped_column(
        ForeignKey("food_items.id"), nullable=True
    )
    added_to_inventory_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True
    )

    purchase: Mapped[GroceryPurchase] = relationship(back_populates="items")
    inventory_item: Mapped[FoodItem | None] = relationship()


class Recipe(Base):
    __tablename__ = "recipes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(180), nullable=False, index=True)
    source: Mapped[str | None] = mapped_column(String(240), nullable=True)
    cuisine: Mapped[str | None] = mapped_column(String(80), nullable=True)
    tags: Mapped[str | None] = mapped_column(String(240), nullable=True)
    servings: Mapped[int | None] = mapped_column(Integer, nullable=True)
    shelf_life_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    calories_per_serving: Mapped[int | None] = mapped_column(
        "calories", Integer, nullable=True
    )
    prep_time_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cook_time_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ingredients: Mapped[str | None] = mapped_column(Text, nullable=True)
    instructions: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    ingredient_items: Mapped[list["RecipeIngredient"]] = relationship(
        back_populates="recipe", cascade="all, delete-orphan"
    )


class RecipeIngredient(Base):
    __tablename__ = "recipe_ingredients"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    recipe_id: Mapped[int] = mapped_column(
        ForeignKey("recipes.id"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    quantity: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    unit: Mapped[str | None] = mapped_column(String(40), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    recipe: Mapped[Recipe] = relationship(back_populates="ingredient_items")


class RestaurantStatus(StrEnum):
    WANT_TO_TRY = "want_to_try"
    VISITED = "visited"
    PERMANENTLY_CLOSED = "permanently_closed"


class RestaurantCategory(StrEnum):
    PARTY_OF_ONE = "party_of_one"
    DATE_NIGHT = "date_night"
    CASUAL_DATES = "casual_dates"
    LINDA_ONLY = "linda_only"
    DESSERT = "dessert"


class Restaurant(Base):
    __tablename__ = "restaurants"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    google_place_id: Mapped[str] = mapped_column(
        String(160), nullable=False, unique=True, index=True
    )
    name: Mapped[str] = mapped_column(String(180), nullable=False, index=True)
    custom_name: Mapped[str | None] = mapped_column(String(180), nullable=True)
    formatted_address: Mapped[str | None] = mapped_column(String(300), nullable=True)
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)
    google_maps_uri: Mapped[str | None] = mapped_column(String(500), nullable=True)
    website_uri: Mapped[str | None] = mapped_column(String(500), nullable=True)
    menu_url: Mapped[str | None] = mapped_column(String(800), nullable=True)
    phone_number: Mapped[str | None] = mapped_column(String(80), nullable=True)
    status: Mapped[RestaurantStatus] = mapped_column(
        Enum(RestaurantStatus), nullable=False, default=RestaurantStatus.WANT_TO_TRY
    )
    category: Mapped[RestaurantCategory | None] = mapped_column(
        Enum(RestaurantCategory), nullable=True
    )
    cuisine: Mapped[str | None] = mapped_column(String(120), nullable=True)
    tags: Mapped[str | None] = mapped_column(String(240), nullable=True)
    neighborhood: Mapped[str | None] = mapped_column(String(120), nullable=True)
    personal_rating: Mapped[int | None] = mapped_column(Integer, nullable=True)
    price_level: Mapped[str | None] = mapped_column(String(40), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    photos: Mapped[list["RestaurantPhoto"]] = relationship(
        back_populates="restaurant",
        cascade="all, delete-orphan",
        order_by="RestaurantPhoto.created_at",
    )
    menu_cache: Mapped["RestaurantMenuCache | None"] = relationship(
        back_populates="restaurant",
        cascade="all, delete-orphan",
        uselist=False,
    )


class RestaurantMenuCache(Base):
    __tablename__ = "restaurant_menu_caches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    restaurant_id: Mapped[int] = mapped_column(
        ForeignKey("restaurants.id"), nullable=False, unique=True, index=True
    )
    source_url: Mapped[str | None] = mapped_column(String(800), nullable=True)
    extracted_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    structured_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="not_fetched")
    last_success_status: Mapped[str | None] = mapped_column(String(40), nullable=True)
    last_success_source_url: Mapped[str | None] = mapped_column(String(800), nullable=True)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    pending_source_url: Mapped[str | None] = mapped_column(String(800), nullable=True)
    pending_extracted_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    pending_content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    fetched_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    restaurant: Mapped[Restaurant] = relationship(back_populates="menu_cache")


class RestaurantPhoto(Base):
    __tablename__ = "restaurant_photos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    restaurant_id: Mapped[int] = mapped_column(
        ForeignKey("restaurants.id"), nullable=False, index=True
    )
    storage_key: Mapped[str] = mapped_column(String(500), nullable=False, unique=True)
    url: Mapped[str] = mapped_column(String(800), nullable=False)
    original_filename: Mapped[str | None] = mapped_column(String(240), nullable=True)
    content_type: Mapped[str] = mapped_column(String(80), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow
    )

    restaurant: Mapped[Restaurant] = relationship(back_populates="photos")
