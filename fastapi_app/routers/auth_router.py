from datetime import datetime
from fastapi import APIRouter, Request, Depends
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from ..database import get_db
from ..dependencies import BaseContext
from ..models import User
from ..auth import check_django_password, make_django_password
from ..templates_config import templates

router = APIRouter(tags=["auth"])


@router.get("/login/", name="login")
async def login_get(request: Request, ctx: BaseContext = Depends(BaseContext)):
    if ctx.current_user:
        return RedirectResponse(request.url_for("home"), status_code=302)
    return templates.TemplateResponse(request, "login.html", ctx.dict(error=None))


@router.post("/login/", name="login_post")
async def login_post(request: Request, ctx: BaseContext = Depends(BaseContext)):
    if ctx.current_user:
        return RedirectResponse(request.url_for("home"), status_code=302)
    form = await request.form()
    username = form.get("username", "").strip()
    password = form.get("password", "")
    user = ctx.db.query(User).filter(User.username == username, User.is_active == True).first()
    if user and check_django_password(password, user.password):
        request.session["user_id"] = user.id
        user.last_login = datetime.utcnow()
        ctx.db.commit()
        if user.is_staff or user.is_superuser:
            # Set cả session key của SQLAdmin để /admin/ nhận ra ngay
            request.session["admin_user"] = user.username
            request.session["admin_id"] = user.id
            return RedirectResponse("/admin/", status_code=302)
        return RedirectResponse(request.url_for("home"), status_code=302)
    return templates.TemplateResponse(request, "login.html", ctx.dict(error="Tên đăng nhập hoặc mật khẩu không đúng!"))


@router.get("/logout/", name="logout")
async def logout(request: Request):
    request.session.pop("user_id", None)
    return RedirectResponse("/login/", status_code=302)


@router.get("/register/", name="register")
async def register_get(request: Request, ctx: BaseContext = Depends(BaseContext)):
    return templates.TemplateResponse(request, "register.html", ctx.dict(errors=[]))


@router.post("/register/", name="register_post")
async def register_post(request: Request, ctx: BaseContext = Depends(BaseContext)):
    form = await request.form()
    username = form.get("username", "").strip()
    email = form.get("email", "").strip()
    first_name = form.get("first_name", "").strip()
    last_name = form.get("last_name", "").strip()
    password1 = form.get("password1", "")
    password2 = form.get("password2", "")

    errors = []
    if not username:
        errors.append("Tên đăng nhập không được để trống.")
    elif ctx.db.query(User).filter(User.username == username).first():
        errors.append("Tên đăng nhập đã tồn tại.")
    if password1 != password2:
        errors.append("Mật khẩu xác nhận không khớp.")
    if len(password1) < 8:
        errors.append("Mật khẩu phải có ít nhất 8 ký tự.")

    if errors:
        return templates.TemplateResponse(request, "register.html", ctx.dict(errors=errors))

    user = User(
        username=username,
        email=email,
        first_name=first_name,
        last_name=last_name,
        password=make_django_password(password1),
    )
    ctx.db.add(user)
    ctx.db.commit()
    return RedirectResponse("/login/", status_code=302)
