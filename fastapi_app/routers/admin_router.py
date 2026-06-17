import os
import json
from datetime import datetime, timedelta
from decimal import Decimal
from fastapi import APIRouter, Request, Depends
from fastapi.responses import RedirectResponse, JSONResponse
from sqlalchemy import func, extract

from ..dependencies import BaseContext
from ..database import get_db
from ..models import User, Order, OrderItem, Product, SupportTicket
from ..email_service import _send
from ..templates_config import templates

router = APIRouter(prefix="/quan-tri", tags=["admin_panel"])

CATEGORY_LABELS = {
    "order_payment": "Đặt hàng / Thanh toán",
    "account": "Tài khoản",
    "cart_product": "Giỏ hàng / Sản phẩm",
    "delivery_warranty": "Giao hàng / Bảo hành",
    "other": "Khác",
}

STATUS_LABELS = {
    "open": ("Chờ xử lý", "#f97316"),
    "in_progress": ("Đang xử lý", "#3b82f6"),
    "resolved": ("Đã giải quyết", "#22c55e"),
    "closed": ("Đã đóng", "#94a3b8"),
}


def _require_admin(ctx: BaseContext):
    if not ctx.current_user or not (ctx.current_user.is_staff or ctx.current_user.is_superuser):
        return RedirectResponse("/login/", status_code=302)
    return None

def _open_count(db) -> int:
    return db.query(func.count(SupportTicket.id)).filter(SupportTicket.status == "open").scalar() or 0


# ─── Dashboard ───────────────────────────────────────────────────────────────

@router.get("/", name="admin_dashboard")
async def dashboard(request: Request, ctx: BaseContext = Depends(BaseContext)):
    redirect = _require_admin(ctx)
    if redirect:
        return redirect

    db = ctx.db
    now = datetime.utcnow()

    # Stats
    total_orders     = db.query(func.count(Order.id)).scalar() or 0
    total_customers  = db.query(func.count(User.id)).filter(User.is_staff == False).scalar() or 0
    total_products   = db.query(func.count(Product.id)).scalar() or 0
    total_stock      = db.query(func.sum(Product.stock)).scalar() or 0
    total_revenue    = db.query(func.sum(OrderItem.quantity * Product.price))\
                         .join(Product, OrderItem.product_id == Product.id)\
                         .join(Order, OrderItem.order_id == Order.id)\
                         .filter(Order.complete == True).scalar() or Decimal("0")
    total_revenue    = int(total_revenue)

    # Order status
    orders_pending   = db.query(func.count(Order.id)).filter(Order.status == "pending", Order.complete == False).scalar() or 0
    orders_approved  = db.query(func.count(Order.id)).filter(Order.status == "approved").scalar() or 0
    orders_canceled  = db.query(func.count(Order.id)).filter(Order.status == "canceled").scalar() or 0

    # Recent orders
    recent_orders = (
        db.query(Order, User.username)
        .outerjoin(User, Order.customer_id == User.id)
        .order_by(Order.date_order.desc())
        .limit(8)
        .all()
    )

    # Top products
    top_products = (
        db.query(Product.id, Product.name, func.sum(OrderItem.quantity).label("sold"))
        .join(OrderItem, Product.id == OrderItem.product_id)
        .group_by(Product.id, Product.name)
        .order_by(func.sum(OrderItem.quantity).desc())
        .limit(5)
        .all()
    )

    # Revenue last 12 months
    months_data = []
    for i in range(11, -1, -1):
        target = now - timedelta(days=i * 30)
        rev = db.query(func.sum(OrderItem.quantity * Product.price))\
                .join(Product, OrderItem.product_id == Product.id)\
                .join(Order, OrderItem.order_id == Order.id)\
                .filter(
                    Order.complete == True,
                    extract("year",  Order.date_order) == target.year,
                    extract("month", Order.date_order) == target.month,
                ).scalar() or Decimal("0")
        months_data.append({"month": target.strftime("%m/%Y"), "revenue": int(rev)})

    # Open tickets
    open_tickets = (
        db.query(SupportTicket)
        .filter(SupportTicket.status == "open")
        .order_by(SupportTicket.created_at.desc())
        .limit(5)
        .all()
    )

    return templates.TemplateResponse(request, "admin_dashboard.html", ctx.dict(
        total_revenue=f"{total_revenue:,.0f}".replace(",", "."),
        total_orders=total_orders,
        total_customers=total_customers,
        total_products=total_products,
        total_stock=total_stock,
        orders_pending=orders_pending,
        orders_approved=orders_approved,
        orders_canceled=orders_canceled,
        recent_orders=recent_orders,
        top_products=top_products,
        months_data=json.dumps(months_data),
        open_tickets=open_tickets,
        open_ticket_count=len(open_tickets),
        category_labels=CATEGORY_LABELS,
        active_page="dashboard",
    ))


# ─── Ticket List ─────────────────────────────────────────────────────────────

@router.get("/tickets/", name="admin_tickets")
async def ticket_list(request: Request, ctx: BaseContext = Depends(BaseContext)):
    redirect = _require_admin(ctx)
    if redirect:
        return redirect

    status_filter = request.query_params.get("status", "")
    q = ctx.db.query(SupportTicket).order_by(SupportTicket.created_at.desc())
    if status_filter:
        q = q.filter(SupportTicket.status == status_filter)
    tickets = q.all()

    return templates.TemplateResponse(request, "admin_tickets.html", ctx.dict(
        tickets=tickets,
        status_filter=status_filter,
        category_labels=CATEGORY_LABELS,
        status_labels=STATUS_LABELS,
        open_ticket_count=_open_count(ctx.db),
        active_page="tickets",
    ))


# ─── Ticket Detail + Reply ────────────────────────────────────────────────────

@router.get("/tickets/{ticket_id}/", name="admin_ticket_detail")
async def ticket_detail(ticket_id: str, request: Request, ctx: BaseContext = Depends(BaseContext)):
    redirect = _require_admin(ctx)
    if redirect:
        return redirect

    ticket = ctx.db.query(SupportTicket).filter(SupportTicket.ticket_id == ticket_id).first()
    if not ticket:
        return RedirectResponse("/quan-tri/tickets/", status_code=302)

    return templates.TemplateResponse(request, "admin_ticket_detail.html", ctx.dict(
        ticket=ticket,
        category_labels=CATEGORY_LABELS,
        status_labels=STATUS_LABELS,
        open_ticket_count=_open_count(ctx.db),
        active_page="tickets",
        success=False,
        error=None,
    ))


@router.post("/tickets/{ticket_id}/reply/", name="admin_ticket_reply")
async def ticket_reply(ticket_id: str, request: Request, ctx: BaseContext = Depends(BaseContext)):
    redirect = _require_admin(ctx)
    if redirect:
        return redirect

    ticket = ctx.db.query(SupportTicket).filter(SupportTicket.ticket_id == ticket_id).first()
    if not ticket:
        return RedirectResponse("/quan-tri/tickets/", status_code=302)

    form = await request.form()
    reply_body  = form.get("reply_body", "").strip()
    new_status  = form.get("new_status", ticket.status)
    admin_name  = ctx.current_user.username if ctx.current_user else "Kỹ thuật viên"

    error = None
    success = False

    if not reply_body:
        error = "Vui lòng nhập nội dung phản hồi."
    elif not ticket.customer_email:
        error = "Ticket này không có email khách hàng."
    else:
        # Update ticket
        ticket.status = new_status
        note_line = f"\n\n[{datetime.utcnow().strftime('%d/%m/%Y %H:%M')} - {admin_name}]:\n{reply_body}"
        ticket.staff_note = (ticket.staff_note or "") + note_line
        ticket.updated_at = datetime.utcnow()
        ctx.db.commit()

        # Send HTML email reply to customer
        cat_label = CATEGORY_LABELS.get(ticket.category, ticket.category)
        body_html = f"""
        <h2>Phản hồi từ Kỹ thuật viên Đà Nẵng Store</h2>
        <p>Xin chào! Chúng tôi đã xem xét yêu cầu hỗ trợ của bạn và có phản hồi như sau:</p>
        <div class="info-box">
          <div class="row"><span class="label">Mã ticket</span><span class="value">{ticket.ticket_id}</span></div>
          <div class="row"><span class="label">Loại vấn đề</span><span class="value">{cat_label}</span></div>
          <div class="row"><span class="label">Trạng thái</span>
            <span class="value" style="color:{'#22c55e' if new_status == 'resolved' else '#3b82f6'};">
              {STATUS_LABELS.get(new_status, (new_status,))[0]}
            </span>
          </div>
        </div>
        <p style="margin:16px 0 6px;font-weight:600;font-size:0.9rem;color:#374151;">Nội dung phản hồi:</p>
        <div class="desc-box">{reply_body}</div>
        <p style="margin-top:20px;font-size:0.88rem;color:#64748b;">
          Nếu cần hỗ trợ thêm, vui lòng gửi yêu cầu mới tại website hoặc gọi hotline <strong>0905 123 456</strong>.
        </p>
        """
        ok = _send(
            to_email=ticket.customer_email,
            subject=f"[Đà Nẵng Store] Phản hồi ticket {ticket.ticket_id}",
            body_html=body_html,
        )
        if ok:
            success = True
        else:
            error = "Gửi email thất bại — kiểm tra cấu hình Gmail trong .env"

    return templates.TemplateResponse(request, "admin_ticket_detail.html", ctx.dict(
        ticket=ticket,
        category_labels=CATEGORY_LABELS,
        status_labels=STATUS_LABELS,
        open_ticket_count=_open_count(ctx.db),
        active_page="tickets",
        success=success,
        error=error,
    ))


@router.post("/tickets/{ticket_id}/status/", name="admin_ticket_status")
async def ticket_status(ticket_id: str, request: Request, ctx: BaseContext = Depends(BaseContext)):
    redirect = _require_admin(ctx)
    if redirect:
        return redirect

    form = await request.form()
    new_status = form.get("status", "open")
    ticket = ctx.db.query(SupportTicket).filter(SupportTicket.ticket_id == ticket_id).first()
    if ticket:
        ticket.status = new_status
        ticket.updated_at = datetime.utcnow()
        ctx.db.commit()

    return RedirectResponse(f"/quan-tri/tickets/{ticket_id}/", status_code=302)
