from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings


class Base(DeclarativeBase):
    pass


def _ensure_sqlite_parent(database_url: str) -> None:
    if not database_url.startswith("sqlite:///"):
        return
    db_path = database_url.removeprefix("sqlite:///")
    if db_path and db_path != ":memory:":
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)


_ensure_sqlite_parent(settings.database_url)

engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False}
    if settings.database_url.startswith("sqlite")
    else {},
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    with SessionLocal() as session:
        yield session


def init_db() -> None:
    from app.models import food  # noqa: F401

    Base.metadata.create_all(bind=engine)
    _ensure_lightweight_schema_updates()


def _ensure_lightweight_schema_updates() -> None:
    if not settings.database_url.startswith("sqlite"):
        return

    with engine.begin() as connection:
        recipe_columns = {
            row[1] for row in connection.execute(text("PRAGMA table_info(recipes)"))
        }
        if recipe_columns and "servings" not in recipe_columns:
            connection.execute(text("ALTER TABLE recipes ADD COLUMN servings INTEGER"))
        if recipe_columns and "shelf_life_days" not in recipe_columns:
            connection.execute(
                text("ALTER TABLE recipes ADD COLUMN shelf_life_days INTEGER")
            )

        grocery_item_columns = {
            row[1]
            for row in connection.execute(
                text("PRAGMA table_info(grocery_purchase_items)")
            )
        }
        if grocery_item_columns and "inventory_item_id" not in grocery_item_columns:
            connection.execute(
                text(
                    "ALTER TABLE grocery_purchase_items "
                    "ADD COLUMN inventory_item_id INTEGER"
                )
            )
        if (
            grocery_item_columns
            and "added_to_inventory_at" not in grocery_item_columns
        ):
            connection.execute(
                text(
                    "ALTER TABLE grocery_purchase_items "
                    "ADD COLUMN added_to_inventory_at DATETIME"
                )
            )

        restaurant_columns = {
            row[1] for row in connection.execute(text("PRAGMA table_info(restaurants)"))
        }
        if restaurant_columns and "category" not in restaurant_columns:
            connection.execute(text("ALTER TABLE restaurants ADD COLUMN category VARCHAR"))
        if restaurant_columns and "custom_name" not in restaurant_columns:
            connection.execute(
                text("ALTER TABLE restaurants ADD COLUMN custom_name VARCHAR")
            )
        if restaurant_columns and "status" in restaurant_columns:
            connection.execute(
                text("UPDATE restaurants SET status = 'VISITED' WHERE status = 'LIKED'")
            )
            connection.execute(
                text(
                    "UPDATE restaurants SET status = 'VISITED' "
                    "WHERE status = 'DIDNT_LIKE'"
                )
            )
            connection.execute(
                text(
                    "UPDATE restaurants SET status = 'VISITED' "
                    "WHERE status = 'FAVORITE'"
                )
            )
            connection.execute(
                text(
                    "UPDATE restaurants SET status = 'VISITED' "
                    "WHERE status = 'SKIP'"
                )
            )
