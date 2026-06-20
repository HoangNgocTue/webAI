from datetime import datetime
from fastapi import APIRouter, Request, Depends, HTTPException, Form
from fastapi.responses import RedirectResponse

from .. import payment_service
from ..dependencies import BaseContext
from ..models import Order, OrderItem, Invoice, Product
from ..templates_config import templates

router = APIRouter(tags=["orders"])


def _finalize_order(db, order: Order) -> Invoice:
    """Đánh dấu đơn hàng hoàn tất và tạo hóa đơn. Dùng chung cho COD và sau khi
    cổng thanh toán xác nhận thành công."""
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
    items = order.order_items
    return templates.TemplateResponse(request, "checkout.html", ctx.dict(order=order, items=items))


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

    order.payment_method = payment_method
    ctx.db.commit()

    amount = int(order.get_cart_total)

    # --- Thanh toán khi nhận hàng (COD): giữ flow cũ, hoàn tất đơn ngay ---
    if payment_method == "cod":
        order.payment_status = "unpaid"  # sẽ thu tiền khi giao hàng
        ctx.db.commit()
        invoice = _finalize_order(ctx.db, order)
        return RedirectResponse(f"/invoice/{invoice.id}/", status_code=302)

    # --- VNPay: redirect sang trang thanh toán sandbox ---
    if payment_method == "vnpay":
        ip_addr = request.client.host if request.client else "127.0.0.1"
        pay_url, txn_ref = payment_service.create_vnpay_payment_url(
            order_id=order.id, amount=amount, ip_addr=ip_addr,
            order_desc=f"Thanh toan don hang #{order.id} - Da Nang Store",
        )
        order.payment_ref = txn_ref
        ctx.db.commit()
        return RedirectResponse(pay_url, status_code=302)

    # --- MoMo: gọi API tạo URL thanh toán sandbox ---
    if payment_method == "momo":
        try:
            pay_url, momo_order_id = await payment_service.create_momo_payment_url(
                order_id=order.id, amount=amount,
                order_desc=f"Thanh toan don hang #{order.id} - Da Nang Store",
            )
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"Không thể kết nối MoMo: {exc}")
        order.payment_ref = momo_order_id
        ctx.db.commit()
        return RedirectResponse(pay_url, status_code=302)

    raise HTTPException(status_code=400, detail="Phương thức thanh toán không hợp lệ")


@router.get("/payment/vnpay/return/", name="vnpay_return")
async def vnpay_return(request: Request, ctx: BaseContext = Depends(BaseContext)):
    """VNPay redirect người dùng về đây sau khi thanh toán (Return URL)."""
    params = dict(request.query_params)

    if not payment_service.verify_vnpay_response(params):
        return templates.TemplateResponse(
            request, "payment_failed.html",
            ctx.dict(reason="Chữ ký xác thực không hợp lệ.")
        )

    txn_ref = params.get("vnp_TxnRef", "")
    order_id = txn_ref.split("-")[0] if "-" in txn_ref else None
    order = ctx.db.query(Order).filter(Order.id == order_id).first() if order_id else None

    if not order:
        return templates.TemplateResponse(
            request, "payment_failed.html",
            ctx.dict(reason="Không tìm thấy đơn hàng tương ứng.")
        )

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
    return templates.TemplateResponse(
        request, "payment_failed.html",
        ctx.dict(reason="Giao dịch VNPay không thành công hoặc đã bị hủy.")
    )


@router.get("/payment/vnpay/ipn/", name="vnpay_ipn")
async def vnpay_ipn(request: Request):
    """
    IPN (Instant Payment Notification) — VNPay gọi server-to-server để xác nhận
    kết quả giao dịch độc lập với Return URL (người dùng có thể đóng trình
    duyệt trước khi redirect về). Phải trả JSON đúng format VNPay yêu cầu.
    """
    from ..database import SessionLocal

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
    """MoMo redirect người dùng về đây sau khi thanh toán (redirectUrl)."""
    params = dict(request.query_params)

    momo_order_id = params.get("orderId", "")
    order_id = momo_order_id.split("-")[0] if "-" in momo_order_id else None
    order = ctx.db.query(Order).filter(Order.id == order_id).first() if order_id else None

    if not order:
        return templates.TemplateResponse(
            request, "payment_failed.html",
            ctx.dict(reason="Không tìm thấy đơn hàng tương ứng.")
        )

    # Kết quả ở Return URL chỉ mang tính hiển thị tạm; trạng thái chính thức
    # nên dựa vào IPN (server-to-server). Ở đây vẫn kiểm tra nhanh resultCode
    # để chuyển hướng người dùng cho mượt.
    if str(params.get("resultCode")) == "0":
        if not order.complete:
            order.payment_status = "paid"
            order.transaction_id = params.get("transId", "")
            order.approved_date = datetime.utcnow()
            ctx.db.commit()
            invoice = _finalize_order(ctx.db, order)
            return RedirectResponse(f"/invoice/{invoice.id}/", status_code=302)
        return RedirectResponse(f"/invoice/{order.invoice.id}/", status_code=302)

    order.payment_status = "failed"
    ctx.db.commit()
    return templates.TemplateResponse(
        request, "payment_failed.html",
        ctx.dict(reason="Giao dịch MoMo không thành công hoặc đã bị hủy.")
    )


@router.post("/payment/momo/ipn/", name="momo_ipn")
async def momo_ipn(request: Request):
    """
    IPN MoMo gọi server-to-server (JSON body) để xác nhận kết quả giao dịch.
    Phải trả HTTP 204/200 nhanh, không nên xử lý nặng ở đây.
    """
    from ..database import SessionLocal

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
