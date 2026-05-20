from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum

from sqlalchemy import Date, DateTime, Enum, ForeignKey, Integer, Numeric, String, Text
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

    purchase: Mapped[GroceryPurchase] = relationship(back_populates="items")


class Recipe(Base):
    __tablename__ = "recipes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(180), nullable=False, index=True)
    source: Mapped[str | None] = mapped_column(String(240), nullable=True)
    cuisine: Mapped[str | None] = mapped_column(String(80), nullable=True)
    tags: Mapped[str | None] = mapped_column(String(240), nullable=True)
    calories: Mapped[int | None] = mapped_column(Integer, nullable=True)
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
