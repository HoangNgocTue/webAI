"""
Tạo tài khoản admin: username=admin, password=123
Chạy bên trong Docker: docker compose exec web python create_admin.py
"""
import sys
import os
sys.path.insert(0, "/app")
os.chdir("/app")

from fastapi_app.database import SessionLocal, engine, Base
from fastapi_app.models import User
from fastapi_app.auth import make_django_password
from sqlalchemy.sql import func

Base.metadata.create_all(bind=engine)
db = SessionLocal()

existing = db.query(User).filter(User.username == "admin").first()
if existing:
    existing.password = make_django_password("123")
    existing.is_staff = True
    existing.is_superuser = True
    existing.is_active = True
    db.commit()
    print("Admin account updated: username=admin, password=123")
else:
    admin = User(
        username="admin",
        email="admin@danangstore.vn",
        first_name="Admin",
        last_name="Store",
        password=make_django_password("123"),
        is_staff=True,
        is_superuser=True,
        is_active=True,
        date_joined=func.now(),
    )
    db.add(admin)
    db.commit()
    print("Admin account created: username=admin, password=123")

db.close()
