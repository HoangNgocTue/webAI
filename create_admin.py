import sys
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)
os.chdir(BASE_DIR)

from fastapi_app.database import SessionLocal, engine, Base
from fastapi_app.admin_utils import DEFAULT_ADMIN_PASSWORD, DEFAULT_ADMIN_USERNAME, ensure_default_admin

Base.metadata.create_all(bind=engine)
db = SessionLocal()

try:
    ensure_default_admin(db)
    db.commit()
    print(f"Admin account ready: username={DEFAULT_ADMIN_USERNAME}, password={DEFAULT_ADMIN_PASSWORD}")
finally:
    db.close()
