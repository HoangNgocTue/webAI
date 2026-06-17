import os
from fastapi import APIRouter, Request, Depends
from fastapi.responses import RedirectResponse

from ..dependencies import BaseContext
from ..models import SupportTicket
from ..email_service import send_email
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

    # Gửi email xác nhận cho khách
    send_email(
        to_email=email,
        subject=f"[Đà Nẵng Store] Mã ticket hỗ trợ của bạn: {ticket.ticket_id}",
        body=(
            f"Xin chào {name},\n\n"
            f"Chúng tôi đã nhận được yêu cầu hỗ trợ của bạn.\n"
            f"Mã ticket: {ticket.ticket_id}\n"
            f"Danh mục: {CATEGORY_CHOICES.get(category, category)}\n\n"
            f"Kỹ thuật viên sẽ liên hệ với bạn trong thời gian sớm nhất.\n\n"
            f"Trân trọng,\nĐà Nẵng Store"
        )
    )

    # Thông báo cho admin
    admin_email = os.getenv("EMAIL_HOST_USER", "")
    if admin_email:
        send_email(
            to_email=admin_email,
            subject=f"[Ticket mới] {ticket.ticket_id} — {CATEGORY_CHOICES.get(category, category)}",
            body=(
                f"Có ticket hỗ trợ mới cần xử lý:\n\n"
                f"Mã ticket : {ticket.ticket_id}\n"
                f"Họ tên   : {name}\n"
                f"Email    : {email}\n"
                f"SĐT      : {phone or 'Không cung cấp'}\n"
                f"Danh mục : {CATEGORY_CHOICES.get(category, category)}\n\n"
                f"Nội dung:\n{description}\n\n"
                f"Xem và xử lý tại: http://localhost:8000/admin/supportticket/details/{ticket.id}"
            )
        )

    return templates.TemplateResponse(
        request, "support_contact.html",
        ctx.dict(categories=CATEGORY_CHOICES, success=True,
                 ticket_id=ticket.ticket_id, errors=[], form_data={})
    )
