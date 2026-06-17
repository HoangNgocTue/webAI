from pathlib import Path
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from .database import engine
from .admin_setup import setup_admin
from .routers import shop, auth_router, cart_router, orders_router, profile_router, pages_router, chatbot_router

BASE_DIR = Path(__file__).resolve().parent.parent

app = FastAPI(
    title="Đà Nẵng Store",
    description="Cửa hàng công nghệ Đà Nẵng — FastAPI Edition",
    version="2.0.0",
)

# Session middleware (must be added before routes are used)
app.add_middleware(
    SessionMiddleware,
    secret_key="danang-store-session-secret-key-2024-change-in-prod",
    max_age=86400,  # 24 hours
)

# Static files — /static serves app/static/ (CSS, JS, images)
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "app" / "static")), name="static")
# /images serves media/product images (MEDIA_ROOT equivalent)
app.mount("/images", StaticFiles(directory=str(BASE_DIR / "app" / "static" / "images")), name="images")

# SQLAdmin — modern admin panel at /admin
setup_admin(app, engine)

# Routers
app.include_router(shop.router)
app.include_router(auth_router.router)
app.include_router(cart_router.router)
app.include_router(orders_router.router)
app.include_router(profile_router.router)
app.include_router(pages_router.router)
app.include_router(chatbot_router.router)
