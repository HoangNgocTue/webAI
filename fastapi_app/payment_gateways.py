import base64
import hashlib
import hmac
import json
import os
from decimal import Decimal
from urllib import parse, request as urlrequest
from uuid import uuid4

from fastapi import Request


def amount_vnd(value) -> int:
    return int(Decimal(str(value or 0)))


def public_base_url(request: Request) -> str:
    configured = os.getenv("PUBLIC_BASE_URL", "").strip().rstrip("/")
    if configured:
        return configured
    return str(request.base_url).rstrip("/")


def _env_or_default(key: str, default: str) -> str:
    return (os.getenv(key) or default).strip()


def _post_json(url: str, payload: dict, headers: dict | None = None, timeout: int = 30) -> dict:
    data = json.dumps(payload).encode("utf-8")
    req = urlrequest.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json", **(headers or {})},
        method="POST",
    )
    with urlrequest.urlopen(req, timeout=timeout) as response:
        body = response.read().decode("utf-8")
    return json.loads(body or "{}")


def _post_form(url: str, payload: dict, headers: dict | None = None, timeout: int = 30) -> dict:
    data = parse.urlencode(payload).encode("utf-8")
    req = urlrequest.Request(
        url,
        data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded", **(headers or {})},
        method="POST",
    )
    with urlrequest.urlopen(req, timeout=timeout) as response:
        body = response.read().decode("utf-8")
    return json.loads(body or "{}")


def create_momo_payment(order, request: Request) -> dict:
    base_url = public_base_url(request)
    amount = amount_vnd(order.get_cart_total)
    transaction_id = f"MOMO-{uuid4().hex[:10].upper()}"

    partner_code = os.getenv("MOMO_PARTNER_CODE", "MOMOBKUN20180529").strip()
    access_key = os.getenv("MOMO_ACCESS_KEY", "klm05TvNBzhg7h7j").strip()
    secret_key = os.getenv("MOMO_SECRET_KEY", "at67qH6mk8w5Y1nAyMoYKMWACiEi2bsa").strip()
    endpoint = _env_or_default("MOMO_ENDPOINT", "https://test-payment.momo.vn/v2/gateway/api/create")
    request_type = _env_or_default("MOMO_REQUEST_TYPE", "payWithATM")

    redirect_url = _env_or_default("MOMO_REDIRECT_URL", f"{base_url}/payment/momo/return/")
    ipn_url = _env_or_default("MOMO_IPN_URL", f"{base_url}/payment/momo/ipn/")
    order_info = f"Thanh toan don hang"

    if not (partner_code and access_key and secret_key and endpoint):
        return {
            "provider": "momo",
            "mode": "simulator",
            "transaction_id": transaction_id,
            "payment_url": f"/payment/momo/sandbox/{order.id}/?tx={transaction_id}",
            "raw": {},
        }

    request_id = transaction_id
    order_id = f"ORDER-{order.id}-{uuid4().hex[:6].upper()}"
    extra_data = ""
    raw_hash = (
        f"accessKey={access_key}&amount={amount}&extraData={extra_data}"
        f"&ipnUrl={ipn_url}&orderId={order_id}&orderInfo={order_info}"
        f"&partnerCode={partner_code}&redirectUrl={redirect_url}"
        f"&requestId={request_id}&requestType={request_type}"
    )
    signature = hmac.new(secret_key.encode("utf-8"), raw_hash.encode("utf-8"), hashlib.sha256).hexdigest()
    payload = {
        "partnerCode": partner_code,
        "partnerName": "DaNangStore",
        "storeId": "DaNangStore",
        "requestId": request_id,
        "amount": amount,
        "orderId": order_id,
        "orderInfo": order_info,
        "redirectUrl": redirect_url,
        "ipnUrl": ipn_url,
        "lang": "vi",
        "extraData": extra_data,
        "requestType": request_type,
        "signature": signature,
    }
    try:
        data = _post_json(endpoint, payload)
        payment_url = data.get("payUrl") or data.get("deeplink") or data.get("qrCodeUrl")
        if payment_url:
            return {
                "provider": "momo",
                "mode": "gateway",
                "transaction_id": request_id,
                "payment_url": payment_url,
                "raw": data,
            }
        payload["gateway_error"] = data
    except Exception as exc:
        payload["gateway_error"] = str(exc)

    return {
        "provider": "momo",
        "mode": "simulator",
        "transaction_id": transaction_id,
        "payment_url": f"/payment/momo/sandbox/{order.id}/?tx={transaction_id}",
        "raw": payload,
    }


def _paypal_api_base() -> str:
    mode = os.getenv("PAYPAL_MODE", "sandbox").strip().lower()
    return "https://api-m.paypal.com" if mode == "live" else "https://api-m.sandbox.paypal.com"


def _paypal_access_token(client_id: str, client_secret: str) -> str:
    token = base64.b64encode(f"{client_id}:{client_secret}".encode("utf-8")).decode("ascii")
    data = _post_form(
        f"{_paypal_api_base()}/v1/oauth2/token",
        {"grant_type": "client_credentials"},
        headers={"Authorization": f"Basic {token}"},
    )
    return data["access_token"]


def create_paypal_payment(order, request: Request) -> dict:
    base_url = public_base_url(request)
    amount = amount_vnd(order.get_cart_total)
    transaction_id = f"PAYPAL-{uuid4().hex[:10].upper()}"
    client_id = (os.getenv("PAYPAL_CLIENT_ID") or os.getenv("PAYPAL_SANDBOX_CLIENT_ID") or "").strip()
    client_secret = (os.getenv("PAYPAL_CLIENT_SECRET") or os.getenv("PAYPAL_SANDBOX_CLIENT_SECRET") or "").strip()
    currency = os.getenv("PAYPAL_CURRENCY", "USD").strip().upper()
    exchange_rate = Decimal(os.getenv("PAYPAL_VND_PER_USD", "25000"))
    paypal_amount = (Decimal(amount) / exchange_rate).quantize(Decimal("0.01"))

    if not (client_id and client_secret):
        return {
            "provider": "paypal",
            "mode": "simulator",
            "transaction_id": transaction_id,
            "payment_url": f"/payment/paypal/sandbox/{order.id}/?tx={transaction_id}",
            "raw": {"currency": currency, "amount": str(paypal_amount)},
        }

    try:
        access_token = _paypal_access_token(client_id, client_secret)
        payload = {
            "intent": "CAPTURE",
            "purchase_units": [
                {
                    "reference_id": str(order.id),
                    "invoice_id": transaction_id,
                    "amount": {"currency_code": currency, "value": str(paypal_amount)},
                }
            ],
            "application_context": {
                "brand_name": "Da Nang Store",
                "landing_page": "LOGIN",
                "user_action": "PAY_NOW",
                "return_url": f"{base_url}/payment/paypal/return/?order_id={order.id}&tx={transaction_id}",
                "cancel_url": f"{base_url}/checkout/",
            },
        }
        data = _post_json(
            f"{_paypal_api_base()}/v2/checkout/orders",
            payload,
            headers={"Authorization": f"Bearer {access_token}"},
        )
        approve_url = next((link["href"] for link in data.get("links", []) if link.get("rel") == "approve"), None)
        if approve_url:
            return {
                "provider": "paypal",
                "mode": "gateway",
                "transaction_id": transaction_id,
                "payment_url": approve_url,
                "raw": data,
            }
        payload["gateway_error"] = data
    except Exception as exc:
        payload = {"gateway_error": str(exc)}

    return {
        "provider": "paypal",
        "mode": "simulator",
        "transaction_id": transaction_id,
        "payment_url": f"/payment/paypal/sandbox/{order.id}/?tx={transaction_id}",
        "raw": payload,
    }
