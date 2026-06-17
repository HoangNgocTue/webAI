import os
from fastapi import APIRouter, Request, Depends
from fastapi.responses import RedirectResponse

from ..dependencies import BaseContext
from ..models import SupportTicket
from ..email_service import send_ticket_confirm, send_ticket_admin_notify
from ..templates_config import templates

router = APIRouter(tags=["support"])

CATEGORY_CHOICES = {
    "order_payment": "Đặt hàng / Thanh toán",
    "account": "Tài khoản",
    "cart_product": "Giỏ hàng / Sản phẩm",
    "delivery_warranty": "Giao hàng / Bảo hành",
    "other": "Khác",
}


@router.get("/lien-he-ky-thuat/", name="support_contact")
async def support_get(request: Request, ctx: BaseContext = Depends(BaseContext)):
    return templates.TemplateResponse(
        request, "support_contact.html",
        ctx.dict(categories=CATEGORY_CHOICES, success=False, ticket_id=None, errors=[])
    )


@router.post("/lien-he-ky-thuat/", name="support_contact_post")
async def support_post(request: Request, ctx: BaseContext = Depends(BaseContext)):
    form = await request.form()
    name       = form.get("name", "").strip()
    email      = form.get("email", "").strip()
    phone      = form.get("phone", "").strip()
    category   = form.get("category", "other")
    description = form.get("description", "").strip()

    errors = []
    if not name:
        errors.append("Vui lòng nhập họ tên.")
    if not email:
        errors.append("Vui lòng nhập email để nhận phản hồi.")
    if not description:
        errors.append("Vui lòng mô tả vấn đề của bạn.")

    if errors:
        return templates.TemplateResponse(
            request, "support_contact.html",
            ctx.dict(categories=CATEGORY_CHOICES, success=False, ticket_id=None, errors=errors,
                     form_data={"name": name, "email": email, "phone": phone,
                                "category": category, "description": description})
        )

    ticket = SupportTicket(
        category=category,
        description=f"Người liên hệ: {name}\nSĐT: {phone or 'Không cung cấp'}\n\n{description}",
        customer_email=email,
        status="open",
    )
    ctx.db.add(ticket)
    ctx.db.commit()
    ctx.db.refresh(ticket)

    category_label = CATEGORY_CHOICES.get(category, category)

    # Gửi email xác nhận HTML cho khách
    send_ticket_confirm(
        to_email=email,
        customer_name=name,
        ticket_id=ticket.ticket_id,
        category_label=category_label,
        description=description,
    )

    # Thông báo HTML cho admin/kỹ thuật viên
    admin_email = os.getenv("EMAIL_HOST_USER", "")
    if admin_email:
        send_ticket_admin_notify(
            admin_email=admin_email,
            ticket_id=ticket.ticket_id,
            customer_name=name,
            customer_email=email,
            customer_phone=phone,
            category_label=category_label,
            description=description,
        )

    return templates.TemplateResponse(
        request, "support_contact.html",
        ctx.dict(categories=CATEGORY_CHOICES, success=True,
                 ticket_id=ticket.ticket_id, errors=[], form_data={})
    )
