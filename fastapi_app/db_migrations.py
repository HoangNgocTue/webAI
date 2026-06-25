from __future__ import annotations

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine


def _table_columns(engine: Engine, table_name: str) -> set[str]:
    inspector = inspect(engine)
    if not inspector.has_table(table_name):
        return set()
    return {column["name"] for column in inspector.get_columns(table_name)}


def _add_column_if_missing(engine: Engine, table_name: str, column_name: str, ddl: str) -> None:
    columns = _table_columns(engine, table_name)
    if not columns or column_name in columns:
        return
    with engine.begin() as connection:
        connection.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {ddl}"))


def run_startup_migrations(engine: Engine) -> None:
    """Small idempotent migrations for existing SQLite/PostgreSQL deployments."""
    datetime_type = "TIMESTAMP" if engine.dialect.name == "postgresql" else "DATETIME"

    _add_column_if_missing(engine, "app_product", "cpu", "cpu VARCHAR(100)")
    _add_column_if_missing(engine, "app_product", "gpu", "gpu VARCHAR(100)")
    _add_column_if_missing(engine, "app_product", "ram", "ram VARCHAR(50)")
    _add_column_if_missing(engine, "app_product", "storage", "storage VARCHAR(50)")
    _add_column_if_missing(engine, "app_product", "stock", "stock INTEGER DEFAULT 10")

    _add_column_if_missing(engine, "app_order", "approved_date", f"approved_date {datetime_type}")
    _add_column_if_missing(engine, "app_order", "status", "status VARCHAR(20) DEFAULT 'pending'")
    _add_column_if_missing(engine, "app_order", "payment_method", "payment_method VARCHAR(20)")
    _add_column_if_missing(engine, "app_order", "payment_status", "payment_status VARCHAR(20) DEFAULT 'unpaid'")
    _add_column_if_missing(engine, "app_order", "payment_ref", "payment_ref VARCHAR(100)")

    _add_column_if_missing(engine, "chatbot_supportticket", "updated_at", f"updated_at {datetime_type}")
    _add_column_if_missing(engine, "chatbot_supportticket", "customer_email", "customer_email VARCHAR(254)")
    _add_column_if_missing(engine, "chatbot_supportticket", "staff_note", "staff_note TEXT")
