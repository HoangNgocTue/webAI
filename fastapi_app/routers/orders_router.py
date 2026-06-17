import json
from datetime import datetime
from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from sqlalchemy import func

from ..database import get_db
from ..dependencies import BaseContext
from ..models import Order, OrderItem, Invoice, Product, User
from ..templates_config import templates

router = APIRouter(tags=["orders"])


@router.get("/checkout/", name="checkout")
async def checkout_get(request: Request, ctx: BaseContext = Depends(BaseContext)):
    if not ctx.current_user:
        return RedirectResponse("/login/", status_code=302)
    order = (
        ctx.db.query(Order)
        .filter(Order.customer_id == ctx.current_user.id, Order.complete == False)
        .first()
    )
    if not order or order.get_cart_items == 0:
        return RedirectResponse("/cart/", status_code=302)
    items = order.order_items
    return templates.TemplateResponse(request, "checkout.html", ctx.dict(order=order, items=items))


@router.post("/checkout/", name="checkout_post")
async def checkout_post(request: Request, ctx: BaseContext = Depends(BaseContext)):
    if not ctx.current_user:
        return RedirectResponse("/login/", status_code=302)
    order = (
        ctx.db.query(Order)
        .filter(Order.customer_id == ctx.current_user.id, Order.complete == False)
        .first()
    )
    if not order:
        return RedirectResponse("/cart/", status_code=302)

    now = datetime.utcnow()
    order.date_order = now
    order.complete = True
    ctx.db.flush()

    invoice = Invoice(
        order_id=order.id,
        invoice_date=now,
        customer_id=ctx.current_user.id,
        total_amount=order.get_cart_total,
    )
    ctx.db.add(invoice)
    ctx.db.commit()
    ctx.db.refresh(invoice)
    return RedirectResponse(f"/invoice/{invoice.id}/", status_code=302)


@router.get("/invoice/{id}/", name="invoice_detail")
async def invoice_detail(id: int, request: Request, ctx: BaseContext = Depends(BaseContext)):
    invoice = ctx.db.query(Invoice).filter(Invoice.id == id).first()
    if not invoice:
        raise HTTPException(status_code=404, detail="Hóa đơn không tồn tại")
    return templates.TemplateResponse(request, "invoice_detail.html", ctx.dict(invoice=invoice))


@router.get("/order-history/", name="order_history")
async def order_history(request: Request, ctx: BaseContext = Depends(BaseContext)):
    if not ctx.current_user:
        return RedirectResponse("/login/", status_code=302)
    orders = (
        ctx.db.query(Order)
        .filter(Order.customer_id == ctx.current_user.id, Order.complete == True)
        .order_by(Order.date_order.desc())
        .all()
    )
    return templates.TemplateResponse(request, "order_history.html", ctx.dict(orders=orders))


@router.get("/admin-dashboard/", name="admin_dashboard")
async def admin_dashboard(request: Request, ctx: BaseContext = Depends(BaseContext)):
    if not ctx.current_user or not (ctx.current_user.is_staff or ctx.current_user.is_superuser):
        raise HTTPException(status_code=403, detail="Không có quyền truy cập")

    db = ctx.db
    total_revenue = db.query(func.sum(Invoice.total_amount)).scalar() or 0
    total_orders = db.query(Order).count()
    orders_pending = db.query(Order).filter(Order.status == "pending").count()
    orders_approved = db.query(Order).filter(Order.status == "approved").count()
    orders_canceled = db.query(Order).filter(Order.status == "canceled").count()
    total_customers = db.query(User).filter(User.is_staff == False).count()
    active_customers = db.query(Order.customer_id).filter(Order.complete == True).distinct().count()
    total_products = db.query(Product).count()
    total_stock = db.query(func.sum(Product.stock)).scalar() or 0

    from datetime import timedelta
    today = datetime.now()
    months_data = []
    for i in range(11, -1, -1):
        month_date = today - timedelta(days=i * 30)
        revenue_month = (
            db.query(func.sum(Invoice.total_amount))
            .filter(Invoice.invoice_date >= month_date.replace(day=1))
            .scalar()
            or 0
        )
        months_data.append({"month": month_date.strftime("%Y-%m"), "revenue": float(revenue_month)})

    top_products = (
        db.query(OrderItem.product_id, Product.name, func.sum(OrderItem.quantity).label("total_qty"))
        .join(Product, OrderItem.product_id == Product.id)
        .group_by(OrderItem.product_id)
        .order_by(func.sum(OrderItem.quantity).desc())
        .limit(5)
        .all()
    )

    return templates.TemplateResponse(
        request,
        "admin_dashboard.html",
        ctx.dict(
            total_revenue=f"{total_revenue:,.0f}".replace(",", "."),
            total_orders=total_orders,
            orders_pending=orders_pending,
            orders_approved=orders_approved,
            orders_canceled=orders_canceled,
            total_customers=total_customers,
            active_customers=active_customers,
            total_products=total_products,
            total_stock=total_stock,
            months_data=json.dumps(months_data),
            top_products=top_products,
        ),
    )
