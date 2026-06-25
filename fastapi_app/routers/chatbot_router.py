import os
import re
import html
import unicodedata

from fastapi import APIRouter, Request, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from ..database import get_db
from ..dependencies import BaseContext
from ..models import ChatHistory, Order, OrderItem, Product, SupportTicket
from ..chatbot_service import get_system_prompt, get_history, save_history
from ..templates_config import templates

router = APIRouter(tags=["chatbot"])


def _chat_messages(system_prompt: str, history: list, user_message: str) -> list:
    return [{"role": "system", "content": system_prompt}] + history + [
        {"role": "user", "content": user_message}
    ]


def _call_claude(system_prompt: str, history: list, user_message: str) -> str | None:
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        return None

    from anthropic import Anthropic

    client = Anthropic(api_key=api_key)
    response = client.messages.create(
        model=os.getenv("CLAUDE_MODEL", "claude-sonnet-4-6"),
        max_tokens=1024,
        system=system_prompt,
        messages=history + [{"role": "user", "content": user_message}],
    )
    return response.content[0].text


def _call_openai(system_prompt: str, history: list, user_message: str) -> str | None:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return None

    from openai import OpenAI

    client = OpenAI(api_key=api_key)
    response = client.chat.completions.create(
        model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
        messages=_chat_messages(system_prompt, history, user_message),
        max_tokens=1024,
    )
    return response.choices[0].message.content or ""


def _call_groq(system_prompt: str, history: list, user_message: str) -> str | None:
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        return None

    from groq import Groq

    client = Groq(api_key=api_key)
    response = client.chat.completions.create(
        model=os.getenv("GROQ_MODEL", "llama-3.1-8b-instant"),
        messages=_chat_messages(system_prompt, history, user_message),
        max_tokens=1024,
    )
    return response.choices[0].message.content or ""


def _call_ai_with_fallback(system_prompt: str, history: list, user_message: str) -> tuple[str | None, str | None]:
    providers = [
        ("Claude", _call_claude),
        ("ChatGPT", _call_openai),
        ("Groq", _call_groq),
    ]

    saw_configured_provider = False
    for provider_name, call_provider in providers:
        try:
            reply = call_provider(system_prompt, history, user_message)
        except Exception as exc:
            saw_configured_provider = True
            print(f"{provider_name} Error: {type(exc).__name__} - {exc}")
            continue

        if reply is None:
            continue

        saw_configured_provider = True
        if reply.strip():
            return reply, provider_name

    if not saw_configured_provider:
        return (
            "Chatbot AI chưa được cấu hình API key. Hãy thêm một trong các key sau vào file `.env`: "
            "`ANTHROPIC_API_KEY`, `OPENAI_API_KEY` hoặc `GROQ_API_KEY`, sau đó khởi động lại server.",
            None,
        )

    return (
        "Tất cả nhà cung cấp AI đang cấu hình đều gặp lỗi. Bạn kiểm tra API key, model và log terminal để biết chi tiết.",
        None,
    )

TYPO_REPLACEMENTS = {
    "saomi": "xiaomi", "xaomi": "xiaomi", "xiaomy": "xiaomi", "siaomi": "xiaomi",
    "samum": "samsung", "samung": "samsung", "samumg": "samsung",
    "saamsum": "samsung", "samsum": "samsung", "sam sung": "samsung", "samxung": "samsung", "sámum": "samsung",
    "ggior hang": "gio hang", "gior hang": "gio hang", "giohang": "gio hang", "gjo hang": "gio hang",
    "dthaoi": "dien thoai", "dthoai": "dien thoai", "dt hoai": "dien thoai", "dien thoa": "dien thoai",
    "lapop": "laptop", "laptp": "laptop", "labtop": "laptop", "latop": "laptop",
}

GENERIC_PRODUCT_WORDS = {
    "toi", "minh", "can", "muon", "tim", "mua", "cho", "xem", "san", "pham",
    "sp", "loai", "may", "cai", "chiec", "hang", "co", "khong", "nao", "tu",
    "hoc", "tap", "sinh", "vien", "re", "hon", "gia", "duoi", "tren", "khoang",
    "tr", "trieu", "trieu", "dong", "vnd",
    "tam", "them", "nua", "tuong", "giong", "voi", "chi", "tiet", "thong", "tin",
}


def _strip_accents(text: str) -> str:
    text = text.replace("đ", "d").replace("Đ", "D")
    return "".join(
        c for c in unicodedata.normalize("NFD", text)
        if unicodedata.category(c) != "Mn"
    )


def _normalize(text: str) -> str:
    value = _strip_accents(text).lower()
    value = re.sub(r"[^a-z0-9\s]", " ", value)
    value = re.sub(r"\s+", " ", value).strip()
    for wrong, right in TYPO_REPLACEMENTS.items():
        value = value.replace(_strip_accents(wrong).lower(), _strip_accents(right).lower())
    return value


def _safe(value) -> str:
    return html.escape(str(value or ""))


def _vnd(value) -> str:
    try:
        return f"{int(float(value)):,}".replace(",", ".") + "đ"
    except Exception:
        return str(value)


def _extract_price_limit(normalized: str) -> tuple[str | None, int | None]:
    match = re.search(r"(duoi|tren|tam|khoang|re hon|gia re|re)\s*(\d+)", normalized)
    if not match:
        return None, None
    number = int(match.group(2))
    amount = number * 1_000_000 if number < 1000 else number
    keyword = match.group(1)
    if keyword in {"duoi", "re hon", "gia re", "re"}:
        return "lte", amount
    if keyword == "tren":
        return "gte", amount
    return "around", amount


def _product_terms(normalized: str) -> list[str]:
    terms = [t for t in normalized.split() if t not in GENERIC_PRODUCT_WORDS and not any(ch.isdigit() for ch in t)]
    if "dien thoai" in normalized:
        terms.extend(["dien", "thoai", "phone"])
    if "laptop" in normalized:
        terms.append("laptop")
    return list(dict.fromkeys(terms))


def _product_blob(product: Product) -> str:
    categories = " ".join(c.name or "" for c in product.categories)
    values = [product.name, product.detail, product.color, product.cpu, product.gpu, product.ram, product.storage, categories]
    return _normalize(" ".join(str(v or "") for v in values))


def _required_product_group(normalized: str) -> str | None:
    if "laptop" in normalized:
        return "laptop"
    if any(term in normalized for term in ["dien thoai", "phone", "iphone"]):
        return "dien thoai"
    if any(term in normalized for term in ["linh kien", "cpu", "gpu", "ram", "ssd", "pc"]):
        return "linh kien"
    if "phu kien" in normalized:
        return "phu kien"
    return None


def _required_brand(normalized: str) -> str | None:
    if "samsung" in normalized:
        return "samsung"
    if "xiaomi" in normalized:
        return "xiaomi"
    if "iphone" in normalized or "apple" in normalized:
        return "apple"
    return None


def _find_products(db: Session, message: str, request: Request, *, detail: bool = False) -> list[Product]:
    normalized = _normalize(message)
    price_mode, price_limit = _extract_price_limit(normalized)
    terms = _product_terms(normalized)
    required_group = _required_product_group(normalized) or request.session.get("last_chat_product_group")
    required_brand = _required_brand(normalized)
    if required_group:
        request.session["last_chat_product_group"] = required_group
    scored = []

    for product in db.query(Product).all():
        blob = _product_blob(product)
        if required_group and required_group not in blob:
            continue
        if required_brand and required_brand not in blob:
            continue

        if price_limit is not None and product.price is not None:
            price = int(float(product.price))
            if price_mode == "lte" and price > price_limit:
                continue
            if price_mode == "gte" and price < price_limit:
                continue
            if price_mode == "around" and abs(price - price_limit) > price_limit * 0.35:
                continue

        score = 0
        for term in terms:
            if term in blob:
                score += 4 if term in _normalize(product.name or "") else 2
        if "re" in normalized and product.price is not None:
            score += max(0, 4 - int(float(product.price)) // 10_000_000)
        if score or not terms:
            scored.append((score, product))

    if not scored:
        return []

    scored.sort(key=lambda item: (-item[0], float(item[1].price or 0)))
    products = [product for _, product in scored]

    if any(word in normalized for word in ["them", "nua", "tuong tu", "khac"]):
        shown = set(request.session.get("last_chat_product_ids", []))
        next_products = [p for p in products if p.id not in shown]
        if next_products:
            products = next_products

    result = products[:1 if detail else 3]
    request.session["last_chat_product_ids"] = [p.id for p in result]
    request.session["last_chat_query"] = normalized
    if required_group:
        request.session["last_chat_product_group"] = required_group
    return result


def _product_card(product: Product, *, detailed: bool = False) -> str:
    specs = []
    if product.cpu:
        specs.append(f"CPU: {_safe(product.cpu)}")
    if product.gpu:
        specs.append(f"GPU: {_safe(product.gpu)}")
    if product.ram:
        specs.append(f"RAM: {_safe(product.ram)}")
    if product.storage:
        specs.append(f"Bộ nhớ: {_safe(product.storage)}")
    if product.stock is not None:
        specs.append(f"Tồn kho: {product.stock}")

    detail_text = _safe(product.detail)
    if detail_text and len(detail_text) > 180 and not detailed:
        detail_text = detail_text[:180] + "..."

    detail_html = f"<p style='margin:6px 0;color:#475569;font-size:0.86rem;'>{detail_text}</p>" if detail_text else ""
    specs_html = "".join(f"<li>{item}</li>" for item in specs[:5])
    return f"""
<div class="chat-product-card" style="background:#fff;border:1px solid #dbe4ea;border-radius:12px;padding:10px;margin:10px 0;max-width:100%;">
  <div style="font-weight:700;color:#0f172a;margin-bottom:3px;">{_safe(product.name)}</div>
  <div style="color:#e11d48;font-weight:800;margin:3px 0;">{_vnd(product.price)}</div>
  <div style="font-size:0.84rem;color:#475569;margin-bottom:7px;">Thông tin sản phẩm</div>
  {detail_html}
  <ul style="margin:4px 0 8px 18px;padding:0;font-size:0.82rem;color:#475569;">{specs_html}</ul>
  <div style="background:#f8fafc;border:1px solid #e5e7eb;border-radius:10px;padding:8px;margin-top:8px;">
    <a href="/detail/?id={product.id}" target="_blank" style="display:block;text-align:center;">
      <img src="{_safe(product.ImageURL)}" alt="{_safe(product.name)}" style="width:100%;max-width:150px;height:110px;object-fit:contain;">
    </a>
    <div style="display:flex;gap:6px;justify-content:center;align-items:center;margin-top:8px;">
    <button type="button" class="chat-action-btn" data-chat-action="add" data-product-id="{product.id}" style="flex:1;border:0;border-radius:8px;background:#4eaeb9;color:white;padding:7px 8px;font-size:0.8rem;font-weight:700;cursor:pointer;">Thêm giỏ</button>
    <a href="/detail/?id={product.id}" target="_blank" style="flex:1;text-align:center;border-radius:8px;background:#eef2f7;color:#0f172a;padding:7px 8px;font-size:0.8rem;font-weight:700;text-decoration:none;">Chi tiết</a>
    </div>
  </div>
</div>
"""


def _render_product_reply(products: list[Product], request: Request | None = None, message: str = "", *, detailed: bool = False) -> str:
    if not products:
        normalized = _normalize(message)
        group = _required_product_group(normalized) or (request.session.get("last_chat_product_group") if request else None)
        brand = _required_brand(normalized)
        if group or brand:
            product_name = " ".join(part for part in [group, brand.title() if brand else None] if part)
            return (
                f"Hiện shop chưa có {product_name} phù hợp hoặc sản phẩm đang hết hàng. "
                "Bạn có thể hỏi sản phẩm cùng giá, rẻ hơn, hoặc nói rõ nhu cầu để mình gợi ý lựa chọn khác."
            )
        return (
            "Mình chưa tìm thấy sản phẩm phù hợp. Bạn thử nói rõ hơn như "
            "`laptop rẻ dưới 15 triệu`, `điện thoại Xiaomi`, `Samsung pin trâu`, "
            "hoặc `còn sản phẩm tương tự không` nhé."
        )
    title = "Mình tìm thấy sản phẩm phù hợp:" if len(products) == 1 else "Mình gợi ý 1-3 sản phẩm phù hợp nhất:"
    return (
        title
        + "".join(_product_card(product, detailed=detailed) for product in products)
        + "<p style='font-size:0.86rem;color:#475569;margin:8px 0 0;'>Muốn xem thêm thì nhắn <b>còn sản phẩm tương tự không</b> hoặc nói rõ mức giá/nhu cầu hơn nhé.</p>"
    )


def _current_cart(db: Session, user_id: int) -> Order | None:
    return db.query(Order).filter(Order.customer_id == user_id, Order.complete == False).first()


def _render_cart_reply(request: Request, db: Session) -> str:
    user_id = request.session.get("user_id")
    if not user_id:
        return 'Bạn cần <a href="/login/">đăng nhập</a> để mình xem giỏ hàng giúp bạn.'

    order = _current_cart(db, user_id)
    if not order or not order.order_items:
        return "Giỏ hàng của bạn đang trống. Bạn có thể hỏi mình `laptop rẻ`, `điện thoại Xiaomi` để mình gợi ý sản phẩm."

    rows = []
    for item in order.order_items:
        product = item.product
        if not product:
            continue
        rows.append(f"""
<div style="background:#fff;border:1px solid #dbe4ea;border-radius:12px;padding:10px;margin:8px 0;">
  <div style="display:flex;gap:10px;align-items:flex-start;">
    <a href="/detail/?id={product.id}" target="_blank">
      <img src="{_safe(product.ImageURL)}" style="width:64px;height:64px;object-fit:contain;border:1px solid #e5e7eb;border-radius:8px;background:#f8fafc;">
    </a>
    <div style="flex:1;min-width:0;">
      <a href="/detail/?id={product.id}" target="_blank" style="font-weight:700;color:#0f172a;text-decoration:none;">{_safe(product.name)}</a>
      <div style="font-size:0.86rem;color:#475569;">Số lượng: <b>{item.quantity}</b></div>
      <div style="font-size:0.86rem;color:#475569;">Thành tiền: <b>{_vnd(item.get_total)}</b></div>
    </div>
  </div>
  <div style="display:flex;gap:6px;justify-content:center;align-items:center;margin-top:9px;">
    <button class="chat-action-btn" data-chat-action="add" data-product-id="{product.id}" style="flex:1;border:0;border-radius:8px;background:#4eaeb9;color:white;padding:7px 8px;font-size:0.8rem;font-weight:700;cursor:pointer;">+ Thêm</button>
    <button class="chat-action-btn" data-chat-action="remove" data-product-id="{product.id}" style="flex:1;border:0;border-radius:8px;background:#e2e8f0;color:#0f172a;padding:7px 8px;font-size:0.8rem;font-weight:700;cursor:pointer;">- Bớt</button>
    <button class="chat-action-btn" data-chat-action="delete" data-product-id="{product.id}" data-product-name="{_safe(product.name)}" style="flex:1;border:0;border-radius:8px;background:#fee2e2;color:#991b1b;padding:7px 8px;font-size:0.8rem;font-weight:700;cursor:pointer;">Xóa</button>
  </div>
</div>
""")
    return (
        f"Giỏ hàng hiện có <b>{order.get_cart_items}</b> sản phẩm, tổng tiền <b>{_vnd(order.get_cart_total)}</b>."
        + "".join(rows)
        + '<a href="/checkout/" style="display:inline-block;margin-top:8px;border-radius:8px;background:#f97316;color:white;padding:7px 12px;font-weight:700;text-decoration:none;">Thanh toán</a>'
    )


def _remember_cart_event(request: Request, product: Product, action: str) -> None:
    events = request.session.get("chat_cart_events", [])
    events.append({
        "product_id": product.id,
        "product_name": product.name,
        "image": product.ImageURL,
        "price": float(product.price or 0),
        "action": action,
    })
    request.session["chat_cart_events"] = events[-20:]


def _cart_events_from_db(request: Request, db: Session, action: str | None = None) -> list[dict]:
    user_id = request.session.get("user_id")
    if not user_id:
        return []

    rows = (
        db.query(ChatHistory)
        .filter(ChatHistory.user_id == user_id)
        .order_by(ChatHistory.created_at.desc())
        .limit(100)
        .all()
    )
    events = []
    for row in rows:
        reply = row.reply or ""
        normalized = _normalize(reply)
        if "gio hang" not in normalized:
            continue
        event_action = None
        if any(term in normalized for term in ["da them", "them"]):
            event_action = "add"
        if any(term in normalized for term in ["da xoa", "xoa toan bo", "khoi gio hang"]):
            event_action = "delete"
        if action and event_action != action:
            continue

        match = re.search(r"<b>(.*?)</b>", reply)
        product_name = html.unescape(match.group(1)) if match else ""
        product = None
        if product_name:
            product = db.query(Product).filter(Product.name == product_name).first()
        if product:
            events.append({
                "product_id": product.id,
                "product_name": product.name,
                "image": product.ImageURL,
                "price": float(product.price or 0),
                "action": event_action,
            })
    return events


def _render_cart_event_history(request: Request, db: Session | None = None, action: str | None = None) -> str:
    events = request.session.get("chat_cart_events", [])
    if action:
        events = [event for event in events if event.get("action") == action]
    if not events and db is not None:
        events = _cart_events_from_db(request, db, action)
    events = list(reversed(events))[:5]
    if not events:
        if action == "delete":
            return "Mình chưa thấy sản phẩm nào vừa bị xóa khỏi giỏ hàng trong phiên chat này."
        if action == "add":
            return "Mình chưa thấy sản phẩm nào vừa được thêm vào giỏ hàng trong phiên chat này."
        return "Mình chưa thấy thao tác giỏ hàng nào gần đây trong phiên chat này."

    title = "Sản phẩm đã xóa khỏi giỏ hàng gần đây:" if action == "delete" else "Sản phẩm đã thêm/thao tác trong giỏ hàng gần đây:"
    rows = []
    for event in events:
        rows.append(f"""
<div style="background:#fff;border:1px solid #dbe4ea;border-radius:12px;padding:10px;margin:8px 0;">
  <div style="display:flex;gap:10px;align-items:flex-start;">
    <a href="/detail/?id={event.get('product_id')}" target="_blank">
      <img src="{_safe(event.get('image'))}" style="width:64px;height:64px;object-fit:contain;border:1px solid #e5e7eb;border-radius:8px;background:#f8fafc;">
    </a>
    <div style="flex:1;min-width:0;">
      <a href="/detail/?id={event.get('product_id')}" target="_blank" style="font-weight:700;color:#0f172a;text-decoration:none;">{_safe(event.get('product_name'))}</a>
      <div style="font-size:0.86rem;color:#475569;">Giá: <b>{_vnd(event.get('price'))}</b></div>
    </div>
  </div>
  <div style="display:flex;gap:6px;justify-content:center;align-items:center;margin-top:9px;">
    <button class="chat-action-btn" data-chat-action="add" data-product-id="{event.get('product_id')}" style="flex:1;border:0;border-radius:8px;background:#4eaeb9;color:white;padding:7px 8px;font-size:0.8rem;font-weight:700;cursor:pointer;">Thêm lại</button>
    <a href="/detail/?id={event.get('product_id')}" target="_blank" style="flex:1;text-align:center;border-radius:8px;background:#eef2f7;color:#0f172a;padding:7px 8px;font-size:0.8rem;font-weight:700;text-decoration:none;">Chi tiết</a>
  </div>
</div>
""")
    return title + "".join(rows)


def _render_history_reply(request: Request, db: Session) -> str:
    user_id = request.session.get("user_id")
    if not user_id:
        return 'Bạn cần <a href="/login/">đăng nhập</a> để xem lịch sử đơn hàng.'

    orders = (
        db.query(Order)
        .filter(Order.customer_id == user_id, Order.complete == True)
        .order_by(Order.date_order.desc())
        .limit(5)
        .all()
    )
    if not orders:
        return "Bạn chưa có đơn hàng hoàn tất nào gần đây."

    lines = ["Lịch sử đơn hàng gần đây:"]
    for order in orders:
        invoice_link = f' | <a href="/invoice/{order.invoice.id}/" target="_blank">Xem hóa đơn</a>' if order.invoice else ""
        lines.append(
            f"<div style='background:#fff;border:1px solid #dbe4ea;border-radius:10px;padding:9px;margin:7px 0;'>"
            f"<b>Đơn #{order.id}</b> - {order.status or 'pending'}<br>"
            f"Số SP: {order.get_cart_items} | Tổng: <b>{_vnd(order.get_cart_total)}</b>{invoice_link}</div>"
        )
    return "".join(lines) + '<a href="/order-history/" target="_blank">Xem tất cả lịch sử đơn hàng</a>'


def _handle_web_intent(request: Request, db: Session, user_message: str) -> str | None:
    normalized = _normalize(user_message)
    cart_related = any(term in normalized for term in ["gio hang", "cart"])
    past_related = any(term in normalized for term in ["truoc do", "gan day", "vua", "da them", "da xoa", "quen"])
    if cart_related and past_related and "xoa" in normalized:
        return _render_cart_event_history(request, db, "delete")
    if cart_related and past_related and any(term in normalized for term in ["them", "da them"]):
        return _render_cart_event_history(request, db, "add")
    if cart_related and past_related:
        return _render_cart_event_history(request, db)
    if cart_related:
        reply = _render_cart_reply(request, db)
        if "xoa" in normalized:
            reply += "<p style='font-size:0.86rem;color:#475569;margin:8px 0 0;'>Nếu muốn xóa sản phẩm, bấm nút <b>Xóa</b> dưới sản phẩm đó. Mình sẽ hỏi xác nhận 2 lần để tránh xóa nhầm.</p>"
        return reply
    if any(term in normalized for term in ["lich su", "don hang gan day", "hoa don", "order history", "gan day", "hom qua", "da mua", "mua gi", "san pham mua"]):
        return _render_history_reply(request, db)

    detail = any(term in normalized for term in ["chi tiet", "thong tin sp", "thong tin san pham", "cau hinh"])
    comparison = any(term in normalized for term in ["tot hon", "nen mua", "trending", "hot", "mau nao tot", "so sanh", "mau nao la mot"])
    explicit_show = any(term in normalized for term in ["xem", "hien", "tim", "mua", "co ", "duoi", "tren", "re", "chi tiet", "san pham", "sp"])
    if comparison and not explicit_show:
        return None

    has_context = bool(request.session.get("last_chat_product_group"))
    has_price_followup = any(term in normalized for term in ["duoi", "tren", "tam", "khoang", "re", "gia"])
    product_intent = detail or has_price_followup or any(term in normalized for term in [
        "san pham", "sp", "laptop", "dien thoai", "xiaomi", "samsung",
        "iphone", "may tinh", "pc", "phu kien", "ram", "ssd", "re", "gia"
    ])
    if product_intent:
        products = _find_products(db, user_message, request, detail=detail)
        return _render_product_reply(products, request, user_message, detailed=detail)
    return None


def _display_history_from_db(request: Request, db: Session) -> list[dict]:
    user_id = request.session.get("user_id")
    if not user_id:
        return request.session.get("chat_display_history", [])

    session_history = request.session.get("chat_display_history", [])
    existing_count = db.query(ChatHistory).filter(ChatHistory.user_id == user_id).count()
    if session_history and existing_count == 0:
        index = 0
        while index < len(session_history):
            current = session_history[index]
            if current.get("type") == "user":
                user_message = current.get("message", "")
                reply = ""
                if index + 1 < len(session_history) and session_history[index + 1].get("type") == "bot":
                    reply = session_history[index + 1].get("message", "")
                    index += 1
                db.add(ChatHistory(user_id=user_id, message=user_message, reply=reply))
            elif current.get("type") == "bot":
                db.add(ChatHistory(user_id=user_id, message="", reply=current.get("message", "")))
            index += 1
        db.commit()

    rows = (
        db.query(ChatHistory)
        .filter(ChatHistory.user_id == user_id)
        .order_by(ChatHistory.created_at.asc(), ChatHistory.id.asc())
        .all()
    )
    history = []
    for row in rows:
        if row.message:
            history.append({"type": "user", "message": row.message})
        if row.reply:
            history.append({"type": "bot", "message": row.reply})
    return history


def _remember_chat(request: Request, db: Session | None, user_message: str, reply: str) -> None:
    history = request.session.get("chat_display_history", [])
    history.append({"type": "user", "message": user_message})
    history.append({"type": "bot", "message": reply})
    request.session["chat_display_history"] = history[-200:]

    user_id = request.session.get("user_id")
    if db is not None and user_id:
        db.add(ChatHistory(user_id=user_id, message=user_message, reply=reply))
        db.commit()


def _remember_bot_message(request: Request, db: Session | None, reply: str) -> None:
    history = request.session.get("chat_display_history", [])
    history.append({"type": "bot", "message": reply})
    request.session["chat_display_history"] = history[-200:]

    user_id = request.session.get("user_id")
    if db is not None and user_id:
        db.add(ChatHistory(user_id=user_id, message="", reply=reply))
        db.commit()


def _clear_chat_context(request: Request) -> None:
    for key in [
        "chat_display_history",
        "chat_history",
        "last_chat_product_ids",
        "last_chat_query",
        "last_chat_product_group",
        "chat_cart_events",
        "pending_email_ticket",
    ]:
        request.session.pop(key, None)


@router.get("/chatbot/", name="chatbot_view")
async def chatbot_view(request: Request, ctx: BaseContext = Depends(BaseContext)):
    return templates.TemplateResponse(request, "chatbot.html", ctx.dict())


@router.get("/api/chatbot/history/", name="chatbot_history")
async def chatbot_history(request: Request, db: Session = Depends(get_db)):
    return JSONResponse({"history": _display_history_from_db(request, db)})


@router.post("/api/chatbot/reset/", name="chatbot_reset")
async def chatbot_reset(request: Request, db: Session = Depends(get_db)):
    user_id = request.session.get("user_id")
    if user_id:
        db.query(ChatHistory).filter(ChatHistory.user_id == user_id).delete()
        db.commit()
    _clear_chat_context(request)
    return JSONResponse({
        "reply": "Đã reset lịch sử trò chuyện. Bạn vẫn có thể hỏi giỏ hàng, đơn hàng gần đây hoặc sản phẩm đã mua nếu đang đăng nhập."
    })


@router.post("/api/chatbot/", name="chatbot_api")
async def chatbot_api(request: Request, db: Session = Depends(get_db)):
    try:
        data = await request.json()
        user_message = data.get("message", "").strip()
    except Exception:
        form = await request.form()
        user_message = (form.get("message") or "").strip()

    if not user_message:
        return JSONResponse({"reply": "Vui lòng nhập tin nhắn."})

    web_reply = _handle_web_intent(request, db, user_message)
    if web_reply:
        _remember_chat(request, db, user_message, web_reply)
        return JSONResponse({"reply": web_reply, "provider": "web"})

    # --- Flow 1: Ticket ID lookup ---
    ticket_id_match = re.search(r"\bTKT-[A-F0-9]{6}\b", user_message.upper())
    if ticket_id_match:
        ticket_id = ticket_id_match.group(0)
        ticket = db.query(SupportTicket).filter(SupportTicket.ticket_id == ticket_id).first()
        if ticket:
            status_map = {
                "open": "🔴 Chờ xử lý",
                "in_progress": "🟡 Đang xử lý",
                "resolved": "🟢 Đã giải quyết",
            }
            reply = (
                f"📋 **Thông tin ticket {ticket.ticket_id}**\n"
                f"- Loại: {ticket.get_category_display()}\n"
                f"- Trạng thái: {status_map.get(ticket.status, ticket.status)}\n"
                f"- Ngày tạo: {ticket.created_at.strftime('%d/%m/%Y %H:%M')}\n"
            )
            if ticket.staff_note:
                reply += f"- Ghi chú nhân viên: {ticket.staff_note}"
            _remember_chat(request, db, user_message, reply)
            return JSONResponse({"reply": reply})
        reply = f"❌ Không tìm thấy ticket **{ticket_id}**. Bạn kiểm tra lại mã ticket nhé."
        _remember_chat(request, db, user_message, reply)
        return JSONResponse({"reply": reply})

    # --- Flow 2: Email for pending ticket ---
    email_match = re.search(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b", user_message)
    pending_ticket_id = request.session.get("pending_email_ticket")
    if email_match and pending_ticket_id:
        email = email_match.group(0)
        ticket = db.query(SupportTicket).filter(SupportTicket.ticket_id == pending_ticket_id).first()
        if ticket:
            ticket.customer_email = email
            db.commit()
            request.session.pop("pending_email_ticket", None)
            reply = (
                f"✅ Đã lưu email **{email}** cho ticket **{pending_ticket_id}**.\n"
                f"Mình sẽ gửi thông báo ngay khi ticket được xử lý nhé! 😊"
            )
            _remember_chat(request, db, user_message, reply)
            return JSONResponse({"reply": reply})

    # --- Flow 3: AI providers with fallback: Claude -> ChatGPT -> Groq ---
    try:
        system_prompt = get_system_prompt(db)
        history = get_history(request)
        reply, provider = _call_ai_with_fallback(system_prompt, history, user_message)

        ticket_info = None
        if provider and "[SUPPORT_TICKET:" in reply:
            match = re.search(r"\[SUPPORT_TICKET:(\w+)\]", reply)
            if match:
                category = match.group(1)
                if category not in SupportTicket.CATEGORY_CHOICES:
                    category = "other"
                ticket = SupportTicket(category=category, description=user_message)
                db.add(ticket)
                db.commit()
                db.refresh(ticket)
                ticket_info = {"ticket_id": ticket.ticket_id, "category": ticket.get_category_display()}
                request.session["pending_email_ticket"] = ticket.ticket_id
                reply = re.sub(r"\s*\[SUPPORT_TICKET:\w+\]", "", reply).strip()
                reply += (
                    f"\n\n📋 Mã ticket của bạn: **{ticket.ticket_id}**\n"
                    f"Nếu muốn nhận thông báo qua email khi được xử lý, "
                    f"hãy nhập địa chỉ email của bạn nhé."
                )

        if provider:
            save_history(request, user_message, reply)
        _remember_chat(request, db, user_message, reply)
        return JSONResponse({"reply": reply, "ticket": ticket_info, "provider": provider})

    except Exception as e:
        print(f"AI Fallback Error: {type(e).__name__} - {e}")
        reply = (
            "AI chatbot đang gặp lỗi khi xử lý yêu cầu. "
            "Bạn kiểm tra API key, model và log terminal để biết chi tiết."
        )
        _remember_chat(request, db, user_message, reply)
        return JSONResponse({"reply": reply})


@router.post("/api/chatbot/cart-action/", name="chatbot_cart_action")
async def chatbot_cart_action(request: Request, db: Session = Depends(get_db)):
    user_id = request.session.get("user_id")
    if not user_id:
        return JSONResponse({
            "reply": 'Bạn cần <a href="/login/">đăng nhập</a> để thao tác giỏ hàng.',
            "cart_items": 0,
        }, status_code=401)

    data = await request.json()
    product_id = int(data.get("productId") or 0)
    action = data.get("action")
    if action not in {"add", "remove", "delete"}:
        return JSONResponse({"reply": "Thao tác giỏ hàng không hợp lệ."}, status_code=400)

    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        return JSONResponse({"reply": "Không tìm thấy sản phẩm này."}, status_code=404)

    order = _current_cart(db, user_id)
    if not order:
        order = Order(customer_id=user_id)
        db.add(order)
        db.flush()

    item = (
        db.query(OrderItem)
        .filter(OrderItem.order_id == order.id, OrderItem.product_id == product.id)
        .first()
    )

    if action == "add":
        if not item:
            item = OrderItem(order_id=order.id, product_id=product.id, quantity=0)
            db.add(item)
            db.flush()
        item.quantity += 1
        _remember_cart_event(request, product, "add")
        message = f"Đã thêm <b>{_safe(product.name)}</b> vào giỏ hàng."
    elif action == "remove":
        if not item:
            message = f"<b>{_safe(product.name)}</b> chưa có trong giỏ hàng."
        else:
            item.quantity -= 1
            if item.quantity <= 0:
                db.delete(item)
                _remember_cart_event(request, product, "delete")
                message = (
                    f"Đã xóa <b>{_safe(product.name)}</b> khỏi giỏ hàng. "
                    f"<button class='chat-action-btn' data-chat-action='add' data-product-id='{product.id}' "
                    "style='border:0;border-radius:8px;background:#4eaeb9;color:white;padding:5px 9px;font-size:0.8rem;font-weight:700;cursor:pointer;'>Thêm lại</button>"
                )
            else:
                _remember_cart_event(request, product, "remove")
                message = f"Đã bớt 1 <b>{_safe(product.name)}</b>."
    else:
        if item:
            db.delete(item)
        _remember_cart_event(request, product, "delete")
        message = (
            f"Đã xóa toàn bộ <b>{_safe(product.name)}</b> khỏi giỏ hàng. "
            f"<button class='chat-action-btn' data-chat-action='add' data-product-id='{product.id}' "
            "style='border:0;border-radius:8px;background:#4eaeb9;color:white;padding:5px 9px;font-size:0.8rem;font-weight:700;cursor:pointer;'>Thêm lại</button>"
        )

    db.commit()
    db.refresh(order)
    _remember_bot_message(request, db, message)
    return JSONResponse({
        "reply": message,
        "cart_items": order.get_cart_items,
        "cart_total": float(order.get_cart_total),
    })
