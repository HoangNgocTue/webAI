from datetime import datetime
from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import RedirectResponse

from ..dependencies import BaseContext
from ..models import Order, OrderItem, Invoice, Product
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


