"""
Migrate data from SQLite (db.sqlite3) to PostgreSQL.

Usage:
  1. Make sure PostgreSQL container is running: docker compose up db -d
  2. Set DATABASE_URL in .env or environment:
       DATABASE_URL=postgresql://danang_user:danang_pass_2024@localhost:5432/danang_store
  3. Run: python migrate_to_postgres.py
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
    print("  Example: DATABASE_URL=postgresql://danang_user:danang_pass_2024@localhost:5432/danang_store")
    raise SystemExit(1)

if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

try:
    from sqlalchemy import create_engine, text
except ImportError:
    print("Run: pip install sqlalchemy psycopg2-binary")
    raise SystemExit(1)

# Import FastAPI models so SQLAlchemy knows the schema
from fastapi_app.database import Base
import fastapi_app.models  # noqa: registers all models

sqlite_conn = sqlite3.connect(str(SQLITE_PATH))
sqlite_conn.row_factory = sqlite3.Row

pg_engine = create_engine(DATABASE_URL, pool_pre_ping=True)

print("Creating tables in PostgreSQL...")
Base.metadata.create_all(bind=pg_engine)
print("Tables created.")

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


def migrate_table(table_name: str):
    cur = sqlite_conn.execute(f"SELECT * FROM {table_name}")
    rows = cur.fetchall()
    if not rows:
        print(f"  {table_name}: 0 rows (skipped)")
        return

    columns = [desc[0] for desc in cur.description]
    placeholders = ", ".join([f":{c}" for c in columns])
    col_names = ", ".join(columns)
    sql = f"INSERT INTO {table_name} ({col_names}) VALUES ({placeholders}) ON CONFLICT DO NOTHING"

    with pg_engine.begin() as conn:
        conn.execute(text(sql), [dict(row) for row in rows])
    print(f"  {table_name}: {len(rows)} rows migrated")


print("\nMigrating data...")
for table in TABLES_IN_ORDER:
    try:
        migrate_table(table)
    except Exception as e:
        print(f"  {table}: ERROR — {e}")

# Reset PostgreSQL sequences so auto-increment IDs don't conflict
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
