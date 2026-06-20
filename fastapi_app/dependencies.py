import secrets
from fastapi import Request, Depends
from sqlalchemy.orm import Session
from .database import get_db
from .models import User, Category, Order
from .cart_utils import get_cart


def get_session_user(request: Request, db: Session) -> User | None:
    user_id = request.session.get("user_id")
    if not user_id:
        return None
    return db.query(User).filter(User.id == user_id, User.is_active == True).first()


class BaseContext:
    """Injects common template context: current_user, categories, cart_items, csrf_token."""

    def __init__(self, request: Request, db: Session = Depends(get_db)):
        self.request = request
        self.db = db

        # Session-based CSRF token
        if "csrf_token" not in request.session:
            request.session["csrf_token"] = secrets.token_hex(32)
        self.csrf_token = request.session["csrf_token"]

        # Current user from session
        self.current_user = get_session_user(request, db)

        # Top-level categories for nav bar
        self.categories = db.query(Category).filter(Category.is_sub == False).all()

        # Cart item count, including guest session carts.
        order, _ = get_cart(db, request, self.current_user)
        self.cart_items = order.get_cart_items if order else 0

    def dict(self, **extra):
        return {
            "request": self.request,
            "current_user": self.current_user,
            "categories": self.categories,
            "cart_items": self.cart_items,
            "csrf_token": self.csrf_token,
            **extra,
        }
