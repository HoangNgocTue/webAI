"""
Migrate data from SQLite (db.sqlite3) to PostgreSQL.

Usage:
  1. Make sure PostgreSQL container is running: docker compose up db -d
  2. Run inside the Docker web container:
       docker cp db.sqlite3 danang_store_web:/app/db.sqlite3
       docker cp migrate_to_postgres.py danang_store_web:/app/migrate_to_postgres.py
       docker compose exec web python migrate_to_postgres.py
"""

import os
import sqlite3
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
SQLITE_PATH = BASE_DIR / "db.sqlite3"

DATABASE_URL = os.getenv("DATABASE_URL", "")
if not DATABASE_URL or DATABASE_URL.startswith("sqlite"):
    print("ERROR: Set DATABASE_URL to a PostgreSQL URL before running this script.")
    raise SystemExit(1)

if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

try:
    from sqlalchemy import create_engine, text
except ImportError:
    print("Run: pip install sqlalchemy psycopg2-binary")
    raise SystemExit(1)

from fastapi_app.database import Base
import fastapi_app.models  # noqa

sqlite_conn = sqlite3.connect(str(SQLITE_PATH))
sqlite_conn.row_factory = sqlite3.Row

pg_engine = create_engine(DATABASE_URL, pool_pre_ping=True)

print("Creating tables in PostgreSQL...")
Base.metadata.create_all(bind=pg_engine)
print("Tables created.")

# Columns that are BOOLEAN in PostgreSQL but INTEGER (0/1) in SQLite
BOOL_COLUMNS = {
    "auth_user":    {"is_superuser", "is_staff", "is_active"},
    "app_category": {"is_sub"},
    "app_product":  {"digital"},
    "app_order":    {"complete"},
}

# Junction table has no id column in SQLAlchemy
JUNCTION_TABLES = {"app_product_category"}


def cast_row(table_name: str, row: dict) -> dict:
    bools = BOOL_COLUMNS.get(table_name, set())
    return {k: bool(v) if k in bools else v for k, v in row.items()}


def migrate_table(table_name: str):
    cur = sqlite_conn.execute(f"SELECT * FROM {table_name}")
    rows = cur.fetchall()
    if not rows:
        print(f"  {table_name}: 0 rows (skipped)")
        return

    columns = [desc[0] for desc in cur.description]

    # Junction table has no id column
    if table_name in JUNCTION_TABLES:
        columns = [c for c in columns if c != "id"]

    placeholders = ", ".join([f":{c}" for c in columns])
    col_names = ", ".join(columns)
    sql = f"INSERT INTO {table_name} ({col_names}) VALUES ({placeholders}) ON CONFLICT DO NOTHING"

    data = [cast_row(table_name, {c: row[c] for c in columns}) for row in rows]

    with pg_engine.begin() as conn:
        conn.execute(text(sql), data)
    print(f"  {table_name}: {len(rows)} rows migrated")


TABLES_IN_ORDER = [
    "auth_user",
    "app_category",
    "app_product",
    "app_product_category",
    "app_order",
    "app_orderitem",
    "app_shippingaddress",
    "app_invoice",
    "chatbot_chathistory",
    "chatbot_supportticket",
]

print("\nMigrating data...")
for table in TABLES_IN_ORDER:
    try:
        migrate_table(table)
    except Exception as e:
        print(f"  {table}: ERROR — {e}")

SEQ_TABLES = [
    "auth_user", "app_category", "app_product", "app_order",
    "app_orderitem", "app_shippingaddress", "app_invoice",
    "chatbot_chathistory", "chatbot_supportticket",
]

print("\nResetting PostgreSQL sequences...")
with pg_engine.begin() as conn:
    for table in SEQ_TABLES:
        try:
            conn.execute(text(
                f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), "
                f"COALESCE(MAX(id), 1)) FROM {table}"
            ))
            print(f"  {table}: sequence reset")
        except Exception as e:
            print(f"  {table}: {e}")

sqlite_conn.close()
print("\nMigration complete!")
