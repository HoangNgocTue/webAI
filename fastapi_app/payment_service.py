"""
payment_service.py
Tích hợp cổng thanh toán VNPay & MoMo (môi trường sandbox/test).

- VNPay: tạo URL thanh toán (redirect), xác thực chữ ký (HMAC-SHA512) khi nhận
  Return URL / IPN.
- MoMo: tạo URL thanh toán qua API "create" (payWithMethod), xác thực chữ ký
  (HMAC-SHA256) khi nhận IPN.

Tài liệu tham khảo:
- VNPay sandbox: https://sandbox.vnpayment.vn/apis/docs/thanh-toan-pay/pay.html
- MoMo sandbox:  https://developers.momo.vn/v3/docs/payment/api/wallet/onepay

Lưu ý: đây là tích hợp cho môi trường TEST (sandbox). Trước khi đưa vào sản
phẩm thật, cần đổi sang Merchant ID / Secret Key / endpoint production và
rà soát lại theo tài liệu chính thức mới nhất của từng cổng.
"""
import hashlib
import hmac
import json
import os
import urllib.parse
from datetime import datetime
from urllib.parse import quote_plus

import httpx

# ----------------------------------------------------------------------------
# Cấu hình (đọc từ biến môi trường — xem .env.example)
# ----------------------------------------------------------------------------

# VNPay sandbox
VNPAY_TMN_CODE = os.getenv("VNPAY_TMN_CODE", "")
VNPAY_HASH_SECRET = os.getenv("VNPAY_HASH_SECRET", "")
VNPAY_PAYMENT_URL = os.getenv(
    "VNPAY_PAYMENT_URL", "https://sandbox.vnpayment.vn/paymentv2/vpcpay.html"
)
VNPAY_RETURN_URL = os.getenv("VNPAY_RETURN_URL", "http://localhost:8000/payment/vnpay/return/")
VNPAY_VERSION = "2.1.0"

# MoMo sandbox
MOMO_PARTNER_CODE = os.getenv("MOMO_PARTNER_CODE", "")
MOMO_ACCESS_KEY = os.getenv("MOMO_ACCESS_KEY", "")
MOMO_SECRET_KEY = os.getenv("MOMO_SECRET_KEY", "")
MOMO_ENDPOINT = os.getenv("MOMO_ENDPOINT", "https://test-payment.momo.vn/v2/gateway/api/create")
MOMO_REDIRECT_URL = os.getenv("MOMO_REDIRECT_URL", "http://localhost:8000/payment/momo/return/")
MOMO_IPN_URL = os.getenv("MOMO_IPN_URL", "http://localhost:8000/payment/momo/ipn/")


# ----------------------------------------------------------------------------
# VNPay
# ----------------------------------------------------------------------------

def _vnpay_sign(params: dict) -> str:
    """Sắp xếp params theo thứ tự alphabet và ký HMAC-SHA512 theo chuẩn VNPay."""
    sorted_items = sorted(params.items())
    query_string = "&".join(f"{k}={quote_plus(str(v))}" for k, v in sorted_items if v != "")
    h = hmac.new(VNPAY_HASH_SECRET.encode("utf-8"), query_string.encode("utf-8"), hashlib.sha512)
    return h.hexdigest()


def create_vnpay_payment_url(order_id: int, amount: int, ip_addr: str, order_desc: str = "") -> str:
    """
    Tạo URL redirect sang trang thanh toán VNPay sandbox.
    `amount` tính bằng VND (số nguyên, chưa nhân 100 — hàm này tự nhân).
    """
    now = datetime.now()
    # txn_ref phải duy nhất cho mỗi lần thanh toán -> ghép order_id + timestamp
    txn_ref = f"{order_id}-{int(now.timestamp())}"

    params = {
        "vnp_Version": VNPAY_VERSION,
        "vnp_Command": "pay",
        "vnp_TmnCode": VNPAY_TMN_CODE,
        "vnp_Amount": str(int(amount) * 100),  # VNPay yêu cầu nhân 100
        "vnp_CurrCode": "VND",
        "vnp_TxnRef": txn_ref,
        "vnp_OrderInfo": order_desc or f"Thanh toan don hang {order_id}",
        "vnp_OrderType": "other",
        "vnp_Locale": "vn",
        "vnp_ReturnUrl": VNPAY_RETURN_URL,
        "vnp_IpAddr": ip_addr or "127.0.0.1",
        "vnp_CreateDate": now.strftime("%Y%m%d%H%M%S"),
    }

    secure_hash = _vnpay_sign(params)
    params["vnp_SecureHash"] = secure_hash

    query = urllib.parse.urlencode(params, quote_via=urllib.parse.quote_plus)
    return f"{VNPAY_PAYMENT_URL}?{query}", txn_ref


def verify_vnpay_response(query_params: dict) -> bool:
    """
    Xác thực chữ ký vnp_SecureHash trả về từ VNPay (Return URL hoặc IPN).
    Trả về True nếu hợp lệ.
    """
    params = dict(query_params)
    received_hash = params.pop("vnp_SecureHash", None)
    params.pop("vnp_SecureHashType", None)
    if not received_hash:
        return False
    calculated_hash = _vnpay_sign(params)
    return hmac.compare_digest(calculated_hash, received_hash)


def is_vnpay_success(query_params: dict) -> bool:
    """vnp_ResponseCode == '00' nghĩa là giao dịch thành công."""
    return query_params.get("vnp_ResponseCode") == "00"


# ----------------------------------------------------------------------------
# MoMo
# ----------------------------------------------------------------------------

def _momo_signature(raw_signature: str, secret_key: str) -> str:
    return hmac.new(
        secret_key.encode("utf-8"), raw_signature.encode("utf-8"), hashlib.sha256
    ).hexdigest()


async def create_momo_payment_url(order_id: int, amount: int, order_desc: str = "") -> tuple[str, str]:
    """
    Gọi API MoMo (sandbox) để tạo URL thanh toán.
    Trả về (pay_url, momo_order_id).
    """
    momo_order_id = f"{order_id}-{int(datetime.now().timestamp())}"
    request_id = momo_order_id
    order_info = order_desc or f"Thanh toan don hang {order_id}"
    extra_data = ""  # base64 string nếu cần đính kèm thêm dữ liệu

    raw_signature = (
        f"accessKey={MOMO_ACCESS_KEY}"
        f"&amount={amount}"
        f"&extraData={extra_data}"
        f"&ipnUrl={MOMO_IPN_URL}"
        f"&orderId={momo_order_id}"
        f"&orderInfo={order_info}"
        f"&partnerCode={MOMO_PARTNER_CODE}"
        f"&redirectUrl={MOMO_REDIRECT_URL}"
        f"&requestId={request_id}"
        f"&requestType=payWithMethod"
    )
    signature = _momo_signature(raw_signature, MOMO_SECRET_KEY)

    payload = {
        "partnerCode": MOMO_PARTNER_CODE,
        "partnerName": "Da Nang Store",
        "storeId": "DaNangStore",
        "requestId": request_id,
        "amount": str(amount),
        "orderId": momo_order_id,
        "orderInfo": order_info,
        "redirectUrl": MOMO_REDIRECT_URL,
        "ipnUrl": MOMO_IPN_URL,
        "lang": "vi",
        "extraData": extra_data,
        "requestType": "payWithMethod",
        "signature": signature,
    }

    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(MOMO_ENDPOINT, json=payload)
        data = resp.json()

    if data.get("resultCode") == 0:
        return data["payUrl"], momo_order_id
    raise RuntimeError(f"MoMo error: {data.get('message', 'Unknown error')}")


def verify_momo_ipn_signature(data: dict) -> bool:
    """
    Xác thực chữ ký IPN trả về từ MoMo.
    Thứ tự field theo đúng tài liệu MoMo (KHÔNG sắp xếp alphabet tự do).
    """
    received_signature = data.get("signature", "")
    raw_signature = (
        f"accessKey={MOMO_ACCESS_KEY}"
        f"&amount={data.get('amount', '')}"
        f"&extraData={data.get('extraData', '')}"
        f"&message={data.get('message', '')}"
        f"&orderId={data.get('orderId', '')}"
        f"&orderInfo={data.get('orderInfo', '')}"
        f"&orderType={data.get('orderType', '')}"
        f"&partnerCode={data.get('partnerCode', '')}"
        f"&payType={data.get('payType', '')}"
        f"&requestId={data.get('requestId', '')}"
        f"&responseTime={data.get('responseTime', '')}"
        f"&resultCode={data.get('resultCode', '')}"
        f"&transId={data.get('transId', '')}"
    )
    calculated_signature = _momo_signature(raw_signature, MOMO_SECRET_KEY)
    return hmac.compare_digest(calculated_signature, received_signature)


def is_momo_success(data: dict) -> bool:
    """resultCode == 0 nghĩa là giao dịch thành công."""
    return str(data.get("resultCode")) == "0"
