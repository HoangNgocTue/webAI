import os
from fastapi import APIRouter, Request, Depends
from ..dependencies import BaseContext
from ..models import SupportTicket
from ..email_service import send_ticket_confirm, send_ticket_admin_notify
from ..templates_config import templates

router = APIRouter(tags=["pages"])

CONTACT_CATEGORY_MAP = {
    "product": ("cart_product", "Tư vấn sản phẩm"),
    "order": ("order_payment", "Hỗ trợ đơn hàng"),
    "warranty": ("delivery_warranty", "Bảo hành / Sửa chữa"),
    "complaint": ("other", "Khiếu nại"),
    "other": ("other", "Khác"),
}


@router.get("/about/", name="about")
async def about(request: Request, ctx: BaseContext = Depends(BaseContext)):
    return templates.TemplateResponse(request, "about.html", ctx.dict())


@router.get("/contact/", name="contact")
async def contact(request: Request, ctx: BaseContext = Depends(BaseContext)):
    return templates.TemplateResponse(
        request,
        "contact.html",
        ctx.dict(success=False, ticket_id=None, errors=[], form_data={}),
    )


@router.post("/contact/", name="contact_post")
async def contact_post(request: Request, ctx: BaseContext = Depends(BaseContext)):
    form = await request.form()
    name = (form.get("name") or "").strip()
    email = (form.get("email") or "").strip()
    phone = (form.get("phone") or "").strip()
    category_key = (form.get("category") or "other").strip()
    message = (form.get("message") or "").strip()

    if ctx.current_user:
        name = name or ctx.current_user.get_full_name or ctx.current_user.username
        email = email or ctx.current_user.email or ""

    errors = []
    if not name:
        errors.append("Vui lòng nhập họ tên.")
    if not email:
        errors.append("Vui lòng nhập email để nhận phản hồi.")
    if not message:
        errors.append("Vui lòng nhập nội dung liên hệ.")

    if errors:
        return templates.TemplateResponse(
            request,
            "contact.html",
            ctx.dict(
                success=False,
                ticket_id=None,
                errors=errors,
                form_data={"name": name, "email": email, "phone": phone, "category": category_key, "message": message},
            ),
        )

    ticket_category, category_label = CONTACT_CATEGORY_MAP.get(category_key, CONTACT_CATEGORY_MAP["other"])
    ticket = SupportTicket(
        category=ticket_category,
        description=f"Nguồn: Form liên hệ website\nNgười liên hệ: {name}\nSĐT: {phone or 'Không cung cấp'}\n\n{message}",
        customer_email=email,
        status="open",
    )
    ctx.db.add(ticket)
    ctx.db.commit()
    ctx.db.refresh(ticket)

    send_ticket_confirm(
        to_email=email,
        customer_name=name,
        ticket_id=ticket.ticket_id,
        category_label=category_label,
        description=message,
    )

    admin_email = os.getenv("EMAIL_HOST_USER", "")
    if admin_email:
        send_ticket_admin_notify(
            admin_email=admin_email,
            ticket_id=ticket.ticket_id,
            customer_name=name,
            customer_email=email,
            customer_phone=phone,
            category_label=category_label,
            description=message,
        )

    return templates.TemplateResponse(
        request,
        "contact.html",
        ctx.dict(success=True, ticket_id=ticket.ticket_id, errors=[], form_data={}),
    )
