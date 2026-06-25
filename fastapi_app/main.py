import os
from pathlib import Path
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from dotenv import load_dotenv

load_dotenv()

from .database import Base, engine
from . import models  # noqa: F401 - registers models for create_all
from .db_migrations import run_startup_migrations
from .routers import shop, auth_router, cart_router, orders_router, profile_router, pages_router, chatbot_router, support_router, admin_router

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.getenv("SECRET_KEY", "danang-store-dev-secret-change-in-production")

app = FastAPI(
    title="Đà Nẵng Store",
    description="Cửa hàng công nghệ Đà Nẵng",
    version="2.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
)

app.add_middleware(
    SessionMiddleware,
    secret_key=SECRET_KEY,
    max_age=86400,
)

STATIC_DIR = BASE_DIR / "static"
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
app.mount("/images", StaticFiles(directory=str(STATIC_DIR / "images")), name="images")


@app.on_event("startup")
async def ensure_database_schema():
    Base.metadata.create_all(bind=engine)
    run_startup_migrations(engine)

app.include_router(shop.router)
app.include_router(auth_router.router)
app.include_router(cart_router.router)
app.include_router(orders_router.router)
app.include_router(profile_router.router)
app.include_router(pages_router.router)
app.include_router(chatbot_router.router)
app.include_router(support_router.router)
app.include_router(admin_router.legacy_router)
app.include_router(admin_router.router)
