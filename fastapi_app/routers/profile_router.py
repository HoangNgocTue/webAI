from fastapi import APIRouter, Request, Depends
from fastapi.responses import RedirectResponse

from ..dependencies import BaseContext
from ..models import Order
from ..auth import check_django_password, make_django_password
from ..templates_config import templates

router = APIRouter(tags=["profile"])


@router.get("/profile/", name="profile")
async def profile_get(request: Request, ctx: BaseContext = Depends(BaseContext)):
    if not ctx.current_user:
        return RedirectResponse("/login/", status_code=302)
    total_orders = (
        ctx.db.query(Order)
        .filter(Order.customer_id == ctx.current_user.id, Order.complete == True)
        .count()
    )
    return templates.TemplateResponse(
        request, "profile.html", ctx.dict(total_orders=total_orders, messages=[])
    )


@router.post("/profile/", name="profile_post")
async def profile_post(request: Request, ctx: BaseContext = Depends(BaseContext)):
    if not ctx.current_user:
        return RedirectResponse("/login/", status_code=302)

    form = await request.form()
    action = form.get("action")
    user = ctx.current_user
    flash_messages = []

    if action == "update_info":
        user.first_name = form.get("first_name", "").strip()
        user.last_name = form.get("last_name", "").strip()
        email = form.get("email", "").strip()
        if email:
            user.email = email
        ctx.db.commit()
        flash_messages = [{"tags": "success", "message": "Cập nhật thông tin thành công!"}]

    elif action == "change_password":
        old_pw = form.get("old_password", "")
        new_pw1 = form.get("new_password1", "")
        new_pw2 = form.get("new_password2", "")
        if not check_django_password(old_pw, user.password):
            flash_messages = [{"tags": "danger", "message": "Mật khẩu hiện tại không đúng."}]
        elif new_pw1 != new_pw2:
            flash_messages = [{"tags": "danger", "message": "Mật khẩu mới không khớp."}]
        elif len(new_pw1) < 8:
            flash_messages = [{"tags": "danger", "message": "Mật khẩu mới phải có ít nhất 8 ký tự."}]
        else:
            user.password = make_django_password(new_pw1)
            ctx.db.commit()
            flash_messages = [{"tags": "success", "message": "Đổi mật khẩu thành công!"}]

    total_orders = (
        ctx.db.query(Order)
        .filter(Order.customer_id == user.id, Order.complete == True)
        .count()
    )
    return templates.TemplateResponse(
        request, "profile.html", ctx.dict(total_orders=total_orders, messages=flash_messages)
    )
