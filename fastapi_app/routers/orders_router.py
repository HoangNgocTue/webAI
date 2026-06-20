from datetime import datetime
from uuid import uuid4
from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import RedirectResponse, JSONResponse

from ..dependencies import BaseContext
from ..models import Order, OrderItem, Invoice, Product
from ..cart_utils import CHECKOUT_NEXT_KEY
from ..payment_gateways import create_momo_payment, create_paypal_payment
from ..templates_config import templates

router = APIRouter(tags=["orders"])

PAYMENT_METHODS = {
    "cod": "Thanh toán tại nơi",
    "bank_transfer": "Chuyển khoản ngân hàng",
    "momo": "MoMo Sandbox",
    "paypal": "PayPal Sandbox",
}


def _active_user_order(ctx: BaseContext) -> Order | None:
    if not ctx.current_user:
        return None
    return (
        ctx.db.query(Order)
        .filter(Order.customer_id == ctx.current_user.id, Order.complete == False)
        .first()
    )


def _complete_order(ctx: BaseContext, order: Order, method: str, transaction_id: str) -> Invoice:
    now = datetime.utcnow()
    order.date_order = now
    order.complete = True
    order.status = "approved" if method in {"cod", "bank_transfer"} else "paid"
    order.approved_date = now
    order.transaction_id = transaction_id
    ctx.db.flush()

    invoice = Invoice(
        order_id=order.id,
        invoice_date=now,
        customer_id=ctx.current_user.id if ctx.current_user else order.customer_id,
        total_amount=order.get_cart_total,
    )
    ctx.db.add(invoice)
    ctx.db.commit()
    ctx.db.refresh(invoice)
    return invoice


@router.get("/checkout/", name="checkout")
async def checkout_get(request: Request, ctx: BaseContext = Depends(BaseContext)):
    if not ctx.current_user:
        request.session[CHECKOUT_NEXT_KEY] = "/checkout/"
        return RedirectResponse("/login/", status_code=302)
    order = _active_user_order(ctx)
    if not order or order.get_cart_items == 0:
        return RedirectResponse("/cart/", status_code=302)
    items = order.order_items
    return templates.TemplateResponse(
        request,
        "checkout.html",
        ctx.dict(order=order, items=items, payment_methods=PAYMENT_METHODS),
    )


@router.post("/checkout/", name="checkout_post")
async def checkout_post(request: Request, ctx: BaseContext = Depends(BaseContext)):
    if not ctx.current_user:
        request.session[CHECKOUT_NEXT_KEY] = "/checkout/"
        return RedirectResponse("/login/", status_code=302)
    form = await request.form()
    method = form.get("payment_method", "cod")
    if method not in PAYMENT_METHODS:
        method = "cod"

    order = _active_user_order(ctx)
    if not order or order.get_cart_items == 0:
        return RedirectResponse("/cart/", status_code=302)

    transaction_id = f"{method.upper()}-{uuid4().hex[:10].upper()}"
    if method in {"momo", "paypal"}:
        payment = create_momo_payment(order, request) if method == "momo" else create_paypal_payment(order, request)
        order.status = "payment_pending"
        order.transaction_id = payment["transaction_id"]
        ctx.db.commit()
        return RedirectResponse(payment["payment_url"], status_code=302)

    invoice = _complete_order(ctx, order, method, transaction_id)
    return RedirectResponse(f"/invoice/{invoice.id}/", status_code=302)


def _normalize_gateway(provider: str | None) -> str:
    return "paypal" if provider in {"paypal", "visa"} else "momo"


@router.get("/payment/sandbox/{order_id}/", name="legacy_payment_sandbox")
async def legacy_payment_sandbox(order_id: int, request: Request):
    provider = _normalize_gateway(request.query_params.get("method"))
    tx = request.query_params.get("tx", "")
    suffix = f"?tx={tx}" if tx else ""
    return RedirectResponse(f"/payment/{provider}/sandbox/{order_id}/{suffix}", status_code=302)


@router.post("/payment/sandbox/{order_id}/confirm/", name="legacy_payment_sandbox_confirm")
async def legacy_payment_sandbox_confirm(order_id: int, request: Request, ctx: BaseContext = Depends(BaseContext)):
    form = await request.form()
    provider = _normalize_gateway(str(form.get("method", "momo")))
    return await payment_sandbox_confirm(provider, order_id, request, ctx)


@router.get("/payment/{provider}/sandbox/{order_id}/", name="payment_sandbox")
async def payment_sandbox(provider: str, order_id: int, request: Request, tx: str = "", ctx: BaseContext = Depends(BaseContext)):
    if not ctx.current_user:
        return RedirectResponse("/login/", status_code=302)
    order = _active_user_order(ctx)
    if not order or order.id != order_id:
        return RedirectResponse("/cart/", status_code=302)
    provider = provider if provider in {"momo", "paypal"} else "momo"
    method_label = PAYMENT_METHODS[provider]
    return templates.TemplateResponse(
        request,
        "payment_sandbox.html",
        ctx.dict(
            order=order,
            provider=provider,
            method=provider,
            method_label=method_label,
            transaction_id=tx or order.transaction_id,
        ),
    )


@router.post("/payment/{provider}/sandbox/{order_id}/confirm/", name="payment_sandbox_confirm")
async def payment_sandbox_confirm(provider: str, order_id: int, request: Request, ctx: BaseContext = Depends(BaseContext)):
    if not ctx.current_user:
        return RedirectResponse("/login/", status_code=302)
    form = await request.form()
    method = provider if provider in {"momo", "paypal"} else form.get("method", "momo")
    order = _active_user_order(ctx)
    if not order or order.id != order_id:
        return RedirectResponse("/cart/", status_code=302)
    transaction_id = order.transaction_id or f"{method.upper()}-{uuid4().hex[:10].upper()}"
    invoice = _complete_order(ctx, order, method, transaction_id)
    return RedirectResponse(f"/payment/{method}/return/?invoice_id={invoice.id}&status=success&tx={transaction_id}", status_code=302)


@router.get("/payment/momo/return/", name="momo_payment_return")
async def momo_payment_return(request: Request, ctx: BaseContext = Depends(BaseContext)):
    invoice_id = int(request.query_params.get("invoice_id") or 0)
    result_code = request.query_params.get("resultCode")
    status = request.query_params.get("status", "success")
    if invoice_id and status == "success":
        return RedirectResponse(f"/invoice/{invoice_id}/", status_code=302)

    order_id = request.query_params.get("orderId", "")
    if result_code in {"0", 0} and ctx.current_user:
        order = _active_user_order(ctx)
        if order:
            invoice = _complete_order(ctx, order, "momo", request.query_params.get("transId") or order.transaction_id or order_id)
            return RedirectResponse(f"/invoice/{invoice.id}/", status_code=302)
    return RedirectResponse("/checkout/", status_code=302)


@router.post("/payment/momo/ipn/", name="momo_payment_ipn")
async def momo_payment_ipn(request: Request, ctx: BaseContext = Depends(BaseContext)):
    data = await request.json()
    order = ctx.db.query(Order).filter(Order.transaction_id == data.get("requestId"), Order.complete == False).first()
    if not order:
        return JSONResponse({"resultCode": 1, "message": "order_not_found"}, status_code=404)
    if str(data.get("resultCode")) != "0":
        return JSONResponse({"resultCode": 2, "message": "payment_not_success"})
    invoice = _complete_order(ctx, order, "momo", str(data.get("transId") or data.get("requestId")))
    return JSONResponse({"resultCode": 0, "message": "success", "invoice_id": invoice.id})


@router.get("/payment/paypal/return/", name="paypal_payment_return")
async def paypal_payment_return(request: Request, ctx: BaseContext = Depends(BaseContext)):
    invoice_id = int(request.query_params.get("invoice_id") or 0)
    status = request.query_params.get("status", "success")
    if invoice_id and status == "success":
        return RedirectResponse(f"/invoice/{invoice_id}/", status_code=302)
    if ctx.current_user:
        order = _active_user_order(ctx)
        if order:
            invoice = _complete_order(ctx, order, "paypal", request.query_params.get("token") or request.query_params.get("tx") or order.transaction_id)
            return RedirectResponse(f"/invoice/{invoice.id}/", status_code=302)
    return RedirectResponse("/checkout/", status_code=302)


@router.post("/payment/paypal/webhook/", name="paypal_payment_webhook")
async def paypal_payment_webhook(request: Request, ctx: BaseContext = Depends(BaseContext)):
    data = await request.json()
    transaction_id = data.get("resource", {}).get("invoice_id") or data.get("transaction_id")
    order = ctx.db.query(Order).filter(Order.transaction_id == transaction_id, Order.complete == False).first()
    if not order:
        return JSONResponse({"ok": False, "error": "order_not_found"}, status_code=404)
    invoice = _complete_order(ctx, order, "paypal", transaction_id)
    return JSONResponse({"ok": True, "invoice_id": invoice.id, "redirect": f"/invoice/{invoice.id}/"})


@router.get("/payment/return/", name="legacy_payment_return")
async def legacy_payment_return(request: Request):
    invoice_id = int(request.query_params.get("invoice_id") or 0)
    if invoice_id:
        return RedirectResponse(f"/invoice/{invoice_id}/", status_code=302)
    return RedirectResponse("/checkout/", status_code=302)


@router.post("/payment/webhook/", name="payment_webhook")
async def payment_webhook(request: Request, ctx: BaseContext = Depends(BaseContext)):
    data = await request.json()
    order_id = data.get("order_id")
    method = data.get("method", "momo")
    transaction_id = data.get("transaction_id") or f"{method.upper()}-{uuid4().hex[:10].upper()}"
    order = ctx.db.query(Order).filter(Order.id == order_id, Order.complete == False).first()
    if not order:
        return JSONResponse({"ok": False, "error": "order_not_found"}, status_code=404)
    invoice = _complete_order(ctx, order, method, transaction_id)
    return JSONResponse({"ok": True, "invoice_id": invoice.id, "redirect": f"/invoice/{invoice.id}/"})


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


