"""
Initialize database tables (run once on fresh deployment).
Works with both SQLite and PostgreSQL.

Usage: python init_db.py
"""
from fastapi_app.database import engine, Base
import fastapi_app.models  # noqa: registers all models
from fastapi_app.db_migrations import run_startup_migrations

Base.metadata.create_all(bind=engine)
run_startup_migrations(engine)
print("Database tables created successfully.")
