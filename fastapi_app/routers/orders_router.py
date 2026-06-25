from datetime import datetime

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse

from .. import payment_service
from ..database import SessionLocal
from ..dependencies import BaseContext
from ..models import Invoice, Order
from ..templates_config import templates

router = APIRouter(tags=["orders"])


def _public_base_url(request: Request) -> str:
    if payment_service.PUBLIC_BASE_URL:
        return payment_service.PUBLIC_BASE_URL.rstrip("/")
    return str(request.base_url).rstrip("/")


def _payment_failed(request: Request, ctx: BaseContext, reason: str):
    return templates.TemplateResponse(
        request,
        "payment_failed.html",
        ctx.dict(reason=reason),
    )


def _finalize_order(db, order: Order) -> Invoice:
    now = datetime.utcnow()
    order.date_order = now
    order.complete = True
    db.flush()

    invoice = Invoice(
        order_id=order.id,
        invoice_date=now,
        customer_id=order.customer_id,
        total_amount=order.get_cart_total,
    )
    db.add(invoice)
    db.commit()
    db.refresh(invoice)
    return invoice


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

    return templates.TemplateResponse(
        request,
        "checkout.html",
        ctx.dict(order=order, items=order.order_items),
    )


@router.post("/checkout/", name="checkout_post")
async def checkout_post(
    request: Request,
    ctx: BaseContext = Depends(BaseContext),
    payment_method: str = Form("cod"),
):
    if not ctx.current_user:
        return RedirectResponse("/login/", status_code=302)

    order = (
        ctx.db.query(Order)
        .filter(Order.customer_id == ctx.current_user.id, Order.complete == False)
        .first()
    )
    if not order:
        return RedirectResponse("/cart/", status_code=302)

    amount = int(order.get_cart_total)
    if amount <= 0:
        return _payment_failed(request, ctx, "Don hang khong co tong tien hop le.")

    order.payment_method = payment_method
    ctx.db.commit()

    if payment_method == "cod":
        order.payment_status = "unpaid"
        ctx.db.commit()
        invoice = _finalize_order(ctx.db, order)
        return RedirectResponse(f"/invoice/{invoice.id}/", status_code=302)

    if payment_method == "vnpay":
        ip_addr = request.client.host if request.client else "127.0.0.1"
        try:
            pay_url, txn_ref = payment_service.create_vnpay_payment_url(
                order_id=order.id,
                amount=amount,
                ip_addr=ip_addr,
                order_desc=f"Thanh toan don hang {order.id} - Da Nang Store",
                return_url=payment_service.absolute_url(
                    "/payment/vnpay/return/", _public_base_url(request)
                ),
            )
        except Exception as exc:
            return _payment_failed(request, ctx, f"Khong the tao thanh toan VNPay: {exc}")

        order.payment_ref = txn_ref
        ctx.db.commit()
        return RedirectResponse(pay_url, status_code=302)

    if payment_method == "momo":
        momo_amount = payment_service.momo_sandbox_amount(amount)
        try:
            pay_url, momo_order_id = await payment_service.create_momo_payment_url(
                order_id=order.id,
                amount=momo_amount,
                order_desc=f"Thanh toan don hang {order.id} - Da Nang Store",
                redirect_url=payment_service.absolute_url(
                    "/payment/momo/return/", _public_base_url(request)
                ),
                ipn_url=payment_service.absolute_url(
                    "/payment/momo/ipn/", _public_base_url(request)
                ),
            )
        except Exception as exc:
            return _payment_failed(request, ctx, f"Khong the tao thanh toan MoMo: {exc}")

        order.payment_ref = momo_order_id
        ctx.db.commit()
        return RedirectResponse(pay_url, status_code=302)

    raise HTTPException(status_code=400, detail="Phuong thuc thanh toan khong hop le")


@router.get("/payment/vnpay/return/", name="vnpay_return")
async def vnpay_return(request: Request, ctx: BaseContext = Depends(BaseContext)):
    params = dict(request.query_params)

    if not payment_service.verify_vnpay_response(params):
        return _payment_failed(request, ctx, "Chu ky xac thuc khong hop le.")

    txn_ref = params.get("vnp_TxnRef", "")
    order_id = txn_ref.split("-")[0] if "-" in txn_ref else None
    order = ctx.db.query(Order).filter(Order.id == order_id).first() if order_id else None
    if not order:
        return _payment_failed(request, ctx, "Khong tim thay don hang tuong ung.")

    if payment_service.is_vnpay_success(params) and not order.complete:
        order.payment_status = "paid"
        order.transaction_id = params.get("vnp_TransactionNo", "")
        order.approved_date = datetime.utcnow()
        ctx.db.commit()
        invoice = _finalize_order(ctx.db, order)
        return RedirectResponse(f"/invoice/{invoice.id}/", status_code=302)

    if order.invoice:
        return RedirectResponse(f"/invoice/{order.invoice.id}/", status_code=302)

    order.payment_status = "failed"
    ctx.db.commit()
    return _payment_failed(request, ctx, "Giao dich VNPay khong thanh cong hoac da bi huy.")


@router.get("/payment/vnpay/ipn/", name="vnpay_ipn")
async def vnpay_ipn(request: Request):
    params = dict(request.query_params)
    db = SessionLocal()
    try:
        if not payment_service.verify_vnpay_response(params):
            return {"RspCode": "97", "Message": "Invalid signature"}

        txn_ref = params.get("vnp_TxnRef", "")
        order_id = txn_ref.split("-")[0] if "-" in txn_ref else None
        order = db.query(Order).filter(Order.id == order_id).first() if order_id else None
        if not order:
            return {"RspCode": "01", "Message": "Order not found"}
        if order.complete:
            return {"RspCode": "02", "Message": "Order already confirmed"}

        if payment_service.is_vnpay_success(params):
            order.payment_status = "paid"
            order.transaction_id = params.get("vnp_TransactionNo", "")
            order.approved_date = datetime.utcnow()
            db.commit()
            _finalize_order(db, order)
            return {"RspCode": "00", "Message": "Confirm Success"}

        order.payment_status = "failed"
        db.commit()
        return {"RspCode": "00", "Message": "Confirm Success"}
    finally:
        db.close()


@router.get("/payment/momo/return/", name="momo_return")
async def momo_return(request: Request, ctx: BaseContext = Depends(BaseContext)):
    params = dict(request.query_params)
    momo_order_id = params.get("orderId", "")
    order_id = momo_order_id.split("-")[0] if "-" in momo_order_id else None
    order = ctx.db.query(Order).filter(Order.id == order_id).first() if order_id else None
    if not order:
        return _payment_failed(request, ctx, "Khong tim thay don hang tuong ung.")

    if str(params.get("resultCode")) == "0":
        if not order.complete:
            order.payment_status = "paid"
            order.transaction_id = params.get("transId", "")
            order.approved_date = datetime.utcnow()
            ctx.db.commit()
            invoice = _finalize_order(ctx.db, order)
            return RedirectResponse(f"/invoice/{invoice.id}/", status_code=302)
        if order.invoice:
            return RedirectResponse(f"/invoice/{order.invoice.id}/", status_code=302)

    order.payment_status = "failed"
    ctx.db.commit()
    return _payment_failed(request, ctx, "Giao dich MoMo khong thanh cong hoac da bi huy.")


@router.post("/payment/momo/ipn/", name="momo_ipn")
async def momo_ipn(request: Request):
    data = await request.json()
    db = SessionLocal()
    try:
        if not payment_service.verify_momo_ipn_signature(data):
            return {"message": "Invalid signature"}

        momo_order_id = data.get("orderId", "")
        order_id = momo_order_id.split("-")[0] if "-" in momo_order_id else None
        order = db.query(Order).filter(Order.id == order_id).first() if order_id else None
        if not order or order.complete:
            return {"message": "Ignored"}

        if payment_service.is_momo_success(data):
            order.payment_status = "paid"
            order.transaction_id = str(data.get("transId", ""))
            order.approved_date = datetime.utcnow()
            db.commit()
            _finalize_order(db, order)
        else:
            order.payment_status = "failed"
            db.commit()
        return {"message": "Confirmed"}
    finally:
        db.close()


@router.get("/invoice/{id}/", name="invoice_detail")
async def invoice_detail(id: int, request: Request, ctx: BaseContext = Depends(BaseContext)):
    invoice = ctx.db.query(Invoice).filter(Invoice.id == id).first()
    if not invoice:
        raise HTTPException(status_code=404, detail="Hoa don khong ton tai")
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
