from datetime import datetime

from sqlalchemy.orm import Session
from sqlalchemy.sql import func

from .auth import check_django_password, make_django_password
from .models import User


DEFAULT_ADMIN_USERNAME = "admin"
DEFAULT_ADMIN_PASSWORD = "admin123"


def ensure_default_admin(db: Session) -> User:
    user = db.query(User).filter(User.username == DEFAULT_ADMIN_USERNAME).first()
    if user:
        if not check_django_password(DEFAULT_ADMIN_PASSWORD, user.password or ""):
            user.password = make_django_password(DEFAULT_ADMIN_PASSWORD)
        user.email = user.email or "admin@danangstore.vn"
        user.first_name = user.first_name or "Admin"
        user.last_name = user.last_name or "Store"
        user.is_staff = True
        user.is_superuser = True
        user.is_active = True
        return user

    user = User(
        username=DEFAULT_ADMIN_USERNAME,
        email="admin@danangstore.vn",
        first_name="Admin",
        last_name="Store",
        password=make_django_password(DEFAULT_ADMIN_PASSWORD),
        is_staff=True,
        is_superuser=True,
        is_active=True,
        date_joined=func.now(),
    )
    db.add(user)
    db.flush()
    return user


def authenticate_admin(db: Session, username: str, password: str) -> User | None:
    username = (username or "").strip()
    if username == DEFAULT_ADMIN_USERNAME and password == DEFAULT_ADMIN_PASSWORD:
        user = ensure_default_admin(db)
        user.last_login = datetime.utcnow()
        db.commit()
        db.refresh(user)
        return user

    user = (
        db.query(User)
        .filter(User.username == username, User.is_active == True)
        .first()
    )
    if user and (user.is_staff or user.is_superuser) and check_django_password(password, user.password or ""):
        user.last_login = datetime.utcnow()
        db.commit()
        db.refresh(user)
        return user
    return None
