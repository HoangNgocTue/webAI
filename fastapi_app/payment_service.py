import hashlib
import hmac
import os
import urllib.parse
from datetime import datetime
from urllib.parse import quote_plus

import httpx
from dotenv import load_dotenv


load_dotenv()


def _env(name: str, default: str = "") -> str:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default
    return value.strip()


def _env_any(names: tuple[str, ...], default: str = "") -> str:
    for name in names:
        value = _env(name)
        if value:
            return value
    return default


PUBLIC_BASE_URL = _env("PUBLIC_BASE_URL", "http://127.0.0.1:8000").rstrip("/")


def absolute_url(path: str, base_url: str | None = None) -> str:
    return f"{(base_url or PUBLIC_BASE_URL).rstrip('/')}{path}"


def _require_config(provider: str, values: dict[str, str]) -> None:
    missing = [name for name, value in values.items() if not value]
    if missing:
        raise RuntimeError(
            f"Thieu cau hinh {provider}: {', '.join(missing)}. "
            "Hay dien thong tin sandbox trong file .env roi khoi dong lai server."
        )


# VNPay sandbox
VNPAY_TMN_CODE = _env_any(("VNPAY_TMN_CODE", "vnp_TmnCode"))
VNPAY_HASH_SECRET = _env_any(("VNPAY_HASH_SECRET", "vnp_HashSecret"))
VNPAY_PAYMENT_URL = _env_any(
    ("VNPAY_PAYMENT_URL", "vnp_Url"),
    "https://sandbox.vnpayment.vn/paymentv2/vpcpay.html",
)
VNPAY_RETURN_URL = _env("VNPAY_RETURN_URL", absolute_url("/payment/vnpay/return/"))
VNPAY_VERSION = "2.1.0"

# MoMo sandbox
MOMO_PARTNER_CODE = _env("MOMO_PARTNER_CODE")
MOMO_ACCESS_KEY = _env("MOMO_ACCESS_KEY")
MOMO_SECRET_KEY = _env("MOMO_SECRET_KEY")
MOMO_ENDPOINT = _env("MOMO_ENDPOINT", "https://test-payment.momo.vn/v2/gateway/api/create")
MOMO_REDIRECT_URL = _env("MOMO_REDIRECT_URL", absolute_url("/payment/momo/return/"))
MOMO_IPN_URL = _env("MOMO_IPN_URL", absolute_url("/payment/momo/ipn/"))
MOMO_REQUEST_TYPE = _env("MOMO_REQUEST_TYPE", "payWithMethod")
MOMO_MIN_AMOUNT = int(_env("MOMO_MIN_AMOUNT", "10000"))
MOMO_MAX_AMOUNT = int(_env("MOMO_MAX_AMOUNT", "50000000"))


def momo_sandbox_amount(amount: int) -> int:
    return max(MOMO_MIN_AMOUNT, min(int(amount), MOMO_MAX_AMOUNT))


def _vnpay_sign(params: dict) -> str:
    sorted_items = sorted(params.items())
    query_string = "&".join(f"{key}={quote_plus(str(value))}" for key, value in sorted_items if value != "")
    digest = hmac.new(
        VNPAY_HASH_SECRET.encode("utf-8"),
        query_string.encode("utf-8"),
        hashlib.sha512,
    )
    return digest.hexdigest()


def create_vnpay_payment_url(
    order_id: int,
    amount: int,
    ip_addr: str,
    order_desc: str = "",
    return_url: str | None = None,
) -> tuple[str, str]:
    _require_config(
        "VNPay",
        {
            "VNPAY_TMN_CODE": VNPAY_TMN_CODE,
            "VNPAY_HASH_SECRET": VNPAY_HASH_SECRET,
            "VNPAY_PAYMENT_URL": VNPAY_PAYMENT_URL,
        },
    )

    now = datetime.now()
    txn_ref = f"{order_id}-{int(now.timestamp())}"
    params = {
        "vnp_Version": VNPAY_VERSION,
        "vnp_Command": "pay",
        "vnp_TmnCode": VNPAY_TMN_CODE,
        "vnp_Amount": str(int(amount) * 100),
        "vnp_CurrCode": "VND",
        "vnp_TxnRef": txn_ref,
        "vnp_OrderInfo": order_desc or f"Thanh toan don hang {order_id}",
        "vnp_OrderType": "other",
        "vnp_Locale": "vn",
        "vnp_ReturnUrl": return_url or VNPAY_RETURN_URL,
        "vnp_IpAddr": ip_addr or "127.0.0.1",
        "vnp_CreateDate": now.strftime("%Y%m%d%H%M%S"),
    }
    params["vnp_SecureHash"] = _vnpay_sign(params)

    query = urllib.parse.urlencode(params, quote_via=urllib.parse.quote_plus)
    return f"{VNPAY_PAYMENT_URL}?{query}", txn_ref


def verify_vnpay_response(query_params: dict) -> bool:
    params = dict(query_params)
    received_hash = params.pop("vnp_SecureHash", None)
    params.pop("vnp_SecureHashType", None)
    if not received_hash:
        return False
    calculated_hash = _vnpay_sign(params)
    return hmac.compare_digest(calculated_hash, received_hash)


def is_vnpay_success(query_params: dict) -> bool:
    return query_params.get("vnp_ResponseCode") == "00"


def _momo_signature(raw_signature: str, secret_key: str) -> str:
    return hmac.new(
        secret_key.encode("utf-8"),
        raw_signature.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


async def create_momo_payment_url(
    order_id: int,
    amount: int,
    order_desc: str = "",
    redirect_url: str | None = None,
    ipn_url: str | None = None,
) -> tuple[str, str]:
    _require_config(
        "MoMo",
        {
            "MOMO_PARTNER_CODE": MOMO_PARTNER_CODE,
            "MOMO_ACCESS_KEY": MOMO_ACCESS_KEY,
            "MOMO_SECRET_KEY": MOMO_SECRET_KEY,
            "MOMO_ENDPOINT": MOMO_ENDPOINT,
        },
    )

    momo_order_id = f"{order_id}-{int(datetime.now().timestamp())}"
    request_id = momo_order_id
    order_info = order_desc or f"Thanh toan don hang {order_id}"
    extra_data = ""
    redirect_url = redirect_url or MOMO_REDIRECT_URL
    ipn_url = ipn_url or MOMO_IPN_URL

    raw_signature = (
        f"accessKey={MOMO_ACCESS_KEY}"
        f"&amount={amount}"
        f"&extraData={extra_data}"
        f"&ipnUrl={ipn_url}"
        f"&orderId={momo_order_id}"
        f"&orderInfo={order_info}"
        f"&partnerCode={MOMO_PARTNER_CODE}"
        f"&redirectUrl={redirect_url}"
        f"&requestId={request_id}"
        f"&requestType={MOMO_REQUEST_TYPE}"
    )
    signature = _momo_signature(raw_signature, MOMO_SECRET_KEY)

    payload = {
        "partnerCode": MOMO_PARTNER_CODE,
        "partnerName": "Da Nang Store",
        "storeId": "DaNangStore",
        "requestId": request_id,
        "amount": int(amount),
        "orderId": momo_order_id,
        "orderInfo": order_info,
        "redirectUrl": redirect_url,
        "ipnUrl": ipn_url,
        "lang": "vi",
        "extraData": extra_data,
        "requestType": MOMO_REQUEST_TYPE,
        "signature": signature,
    }

    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(MOMO_ENDPOINT, json=payload)
        data = resp.json()

    if data.get("resultCode") == 0:
        return data["payUrl"], momo_order_id
    message = data.get("message") or data.get("localMessage") or "Unknown error"
    raise RuntimeError(f"MoMo error: {message}")


def verify_momo_ipn_signature(data: dict) -> bool:
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
    return str(data.get("resultCode")) == "0"
