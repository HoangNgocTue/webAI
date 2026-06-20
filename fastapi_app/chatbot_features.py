import json
import re
import unicodedata
from decimal import Decimal

from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload

from .models import ChatHistory, Category, Order, OrderItem, Product, User
from .cart_utils import get_cart, update_cart_item


PRICE_UNIT = Decimal("1000000")
PRODUCT_MARKER_RE = re.compile(r"<!--\s*PRODUCT:(\d+)\s*-->")
DETAIL_MARKDOWN_LINK_RE = re.compile(
    r"\s*-?\s*\[(?:Xem chi tiết|Xem sản phẩm)\]\(/detail/\?id=\d+\)",
    re.IGNORECASE,
)
INTERNAL_ABSOLUTE_URL_RE = re.compile(
    r"https?://(?:www\.)?(?:danangstore\.vn|localhost(?::\d+)?|127\.0\.0\.1(?::\d+)?)(/[\w\-./?=&%#]*)",
    re.IGNORECASE,
)
CATEGORY_URL_RE = re.compile(r"/category/?\?category=([^)\s]+)")
BROKEN_LOGIN_RE = re.compile(r"\]\((?:https?://[^)\s]+)?/login\)", re.IGNORECASE)
BARE_LOGIN_RE = re.compile(r"(?<![\w/])/(login|register|cart|checkout|profile|order-history)(?!/)(?=[\s).,]|$)", re.IGNORECASE)
PRODUCT_LINK_LINE_RE = re.compile(r"(?:\s*\|\s*)?Link:\s*/detail/\?id=(\d+)", re.IGNORECASE)
CATEGORY_SLUG_RE = re.compile(r"category/(laptop|dien-thoai|linh-kien-pc|phu-kien)(?![/?\w-])", re.IGNORECASE)
CATEGORY_SLUGS = {"laptop", "dien-thoai", "linh-kien-pc", "phu-kien"}


def normalize_text(value: str) -> str:
    value = unicodedata.normalize("NFD", value or "")
    value = "".join(ch for ch in value if unicodedata.category(ch) != "Mn")
    return value.replace("đ", "d").replace("Đ", "D").lower()


def clean_intent_text(message: str) -> str:
    normalized = normalize_text(message)
    normalized = re.sub(r"[^\w\s]", " ", normalized)
    return re.sub(r"\s+", " ", normalized).strip()


def get_current_user(request, db: Session) -> User | None:
    user_id = request.session.get("user_id")
    if not user_id:
        return None
    return db.query(User).filter(User.id == user_id, User.is_active == True).first()


def product_categories(product: Product) -> str:
    return ", ".join(category.name for category in product.categories) or "Chưa phân loại"


def color_display(value: str | None) -> str:
    colors = {
        "space_gray": "Xám không gian",
        "black": "Đen",
        "white": "Trắng",
        "silver": "Bạc",
        "gold": "Vàng",
        "gray": "Xám",
        "blue": "Xanh dương",
        "green": "Xanh lá",
        "red": "Đỏ",
    }
    return colors.get(value or "", value or "")


def fmt_price(value) -> str:
    try:
        return f"{int(Decimal(str(value))):,}".replace(",", ".")
    except Exception:
        return str(value)


def get_special_reply(message: str) -> str | None:
    normalized = clean_intent_text(message)
    greetings = {"hi", "hello", "hey", "chao", "xin chao", "chao shop", "shop oi", "alo", "alo shop"}
    thanks = {"cam on", "thanks", "thank you", "tks", "ok cam on", "cam on shop"}
    goodbyes = {"bye", "tam biet", "hen gap lai", "chao tam biet"}

    if normalized in greetings:
        return (
            "Xin chào! Mình là Dani của Đà Nẵng Store. "
            "Bạn cần tư vấn laptop, điện thoại, linh kiện PC hay phụ kiện ạ?"
        )
    if normalized in thanks:
        return "Rất vui được hỗ trợ bạn. Khi cần tìm sản phẩm theo giá hoặc cấu hình, cứ nhắn mình nhé!"
    if normalized in goodbyes:
        return "Cảm ơn bạn đã ghé Đà Nẵng Store. Hẹn gặp lại bạn nhé!"
    if any(keyword in normalized for keyword in ["hotline", "so dien thoai", "lien he"]):
        return "Hotline Đà Nẵng Store: 0905 123 456. Bạn có thể gọi để được hỗ trợ nhanh hơn."
    if any(keyword in normalized for keyword in ["dia chi", "o dau", "cua hang"]):
        return "Đà Nẵng Store ở 123 Nguyễn Văn Linh, Đà Nẵng."
    if any(keyword in normalized for keyword in ["bao hanh", "doi tra"]):
        return "Chính sách bên mình: bảo hành 12 tháng và đổi trả trong 7 ngày nếu sản phẩm đủ điều kiện."
    if any(keyword in normalized for keyword in ["ship", "giao hang", "van chuyen"]):
        return "Đà Nẵng Store miễn phí ship cho đơn hàng trên 1 triệu. Đơn dưới 1 triệu sẽ tính phí theo khu vực."
    if any(keyword in normalized for keyword in ["huong dan", "ban lam duoc gi", "giup gi", "tro giup"]):
        return (
            "Bạn có thể hỏi mình: **laptop dưới 15 triệu**, **điện thoại tầm 5 triệu**, "
            "**máy core i7 card RTX**, hoặc **thêm sản phẩm số 1 vào giỏ**."
        )
    return None


def is_auth_request(message: str) -> bool:
    normalized = clean_intent_text(message)
    return any(
        keyword in normalized
        for keyword in [
            "dang nhap",
            "login",
            "tai khoan",
            "account",
            "lich su mua hang",
            "quan ly don hang",
            "don hang cua toi",
        ]
    )


def build_auth_reply() -> str:
    return (
        "Bạn có thể đăng nhập tài khoản tại đây:\n\n"
        "[Đăng nhập](/login/)\n\n"
        "Sau khi đăng nhập, bạn có thể xem lịch sử mua hàng, quản lý đơn hàng và truy cập thông tin cá nhân."
    )


def normalize_internal_links(reply: str) -> str:
    reply = INTERNAL_ABSOLUTE_URL_RE.sub(lambda match: match.group(1), reply or "")
    reply = BROKEN_LOGIN_RE.sub("](/login/)", reply)
    reply = CATEGORY_URL_RE.sub(lambda match: f"/category/?category={match.group(1)}", reply)
    reply = CATEGORY_SLUG_RE.sub(lambda match: f"category/?category={match.group(1)}", reply)
    reply = BARE_LOGIN_RE.sub(lambda match: f"/{match.group(1).lower()}/", reply)
    return reply


def sanitize_bot_reply(reply: str, products: list[Product] | None = None) -> str:
    reply = normalize_internal_links(reply)
    reply = PRODUCT_LINK_LINE_RE.sub("", reply)
    reply = re.sub(r"\[ID:(\d+)\]\s*", "", reply, flags=re.IGNORECASE)
    reply = re.sub(r"\n{3,}", "\n\n", reply).strip()
    if products:
        reply = ensure_product_markers(reply, products)
    return reply


def parse_price_filters(text: str) -> dict:
    filters = {}
    normalized = normalize_text(text)
    unit = r"(?:trieu|tr|m|cu)"

    range_match = re.search(rf"(\d+(?:[.,]\d+)?)\s*(?:den|toi|-)\s*(\d+(?:[.,]\d+)?)\s*{unit}", normalized)
    if range_match:
        low = Decimal(range_match.group(1).replace(",", ".")) * PRICE_UNIT
        high = Decimal(range_match.group(2).replace(",", ".")) * PRICE_UNIT
        filters["price_min"] = min(low, high)
        filters["price_max"] = max(low, high)
        return filters

    amount_match = re.search(rf"(\d+(?:[.,]\d+)?)\s*{unit}", normalized)
    if not amount_match:
        return filters

    amount = Decimal(amount_match.group(1).replace(",", ".")) * PRICE_UNIT
    if any(word in normalized for word in ["duoi", "dung cu", "re hon", "nho hon", "<"]):
        filters["price_max"] = amount
    elif any(word in normalized for word in ["tren", "cao hon", "lon hon", ">"]):
        filters["price_min"] = amount
    elif any(word in normalized for word in ["tam", "khoang", "gan"]):
        filters["price_min"] = amount * Decimal("0.8")
        filters["price_max"] = amount * Decimal("1.2")
    return filters


def parse_product_filters(message: str) -> dict:
    normalized = normalize_text(message)
    filters = parse_price_filters(message)
    categories = {
        "laptop": ["laptop", "may tinh", "may tinh xach tay", "notebook", "macbook"],
        "dien-thoai": ["dien thoai", "ddienhj thoai", "thoai", "dt", "smartphone", "phone", "iphone", "samsung", "samung", "xiaomi"],
        "linh-kien-pc": ["linh kien", "cpu", "gpu", "card", "card do hoa", "ram", "pc"],
        "phu-kien": ["phu kien", "chuot", "ban phim", "tai nghe"],
    }
    for slug, keywords in categories.items():
        if any(f"khong {keyword}" in normalized or f"ko {keyword}" in normalized for keyword in keywords):
            filters["exclude_category_slug"] = slug
            break
        if any(keyword in normalized for keyword in keywords):
            filters["category_slug"] = slug
            break

    colors = [
        ("space_gray", ["xam khong gian", "space gray"]),
        ("black", ["den", "black"]),
        ("white", ["trang", "white"]),
        ("silver", ["bac", "silver"]),
        ("gold", ["vang", "gold"]),
        ("gray", ["xam", "gray", "grey"]),
        ("blue", ["xanh duong", "blue"]),
        ("green", ["xanh la", "green"]),
        ("red", ["do", "red"]),
    ]
    for color, keywords in colors:
        if any(keyword in normalized for keyword in keywords):
            filters["color"] = color
            break
    if "color" not in filters and re.search(r"\bxanh\b", normalized):
        filters["colors"] = ["blue", "green"]

    cpu_match = re.search(r"\b(i[3579]|core\s*i[3579]|ryzen\s*[3579]|m[1234]|snapdragon\s*\w+)\b", normalized)
    if cpu_match:
        filters["cpu"] = cpu_match.group(1).replace("core ", "")
    gpu_match = re.search(r"\b(rtx\s*\d{0,4}|gtx\s*\d{0,4}|nvidia|radeon|apple gpu|adreno)\b", normalized)
    if gpu_match:
        filters["gpu"] = gpu_match.group(1)
    if any(keyword in normalized for keyword in ["gaming", "choi game", "game", "do hoa", "render"]):
        filters.setdefault("category_slug", "laptop")
        filters.setdefault("gpu", "rtx")
    if any(keyword in normalized for keyword in ["hoc tap", "sinh vien", "van phong", "lam viec"]):
        filters.setdefault("category_slug", "laptop")
    brand_aliases = {
        "samsung": ["samsung", "samung", "samsumg", "sámung"],
        "xiaomi": ["xiaomi", "xiomi"],
        "iphone": ["iphone", "ipone"],
        "apple": ["apple"],
        "macbook": ["macbook"],
        "asus": ["asus"],
        "hp": ["hp"],
        "dell": ["dell"],
        "lenovo": ["lenovo"],
        "acer": ["acer"],
        "msi": ["msi"],
    }
    for brand, aliases in brand_aliases.items():
        if any(alias in normalized for alias in aliases):
            filters["name"] = brand
            break
    ram_match = re.search(r"\b(8|12|16|24|32|64)\s*gb\s*(?:ram)?\b", normalized)
    if ram_match:
        filters["ram"] = f"{ram_match.group(1)}GB"
    storage_match = re.search(r"\b(128|256|512)\s*gb|(\d+)\s*tb\b", normalized)
    if storage_match:
        filters["storage"] = storage_match.group(0).upper().replace(" ", "")
    return filters


def filter_products(db: Session, filters: dict):
    query = db.query(Product).options(joinedload(Product.categories))
    if filters.get("price_min"):
        query = query.filter(Product.price >= Decimal(str(filters["price_min"])))
    if filters.get("price_max"):
        query = query.filter(Product.price <= Decimal(str(filters["price_max"])))
    if filters.get("category_slug"):
        query = query.join(Product.categories).filter(Category.slug == filters["category_slug"])
    if filters.get("exclude_category_slug"):
        excluded = db.query(Product.id).join(Product.categories).filter(Category.slug == filters["exclude_category_slug"])
        query = query.filter(~Product.id.in_(excluded))
    if filters.get("color"):
        query = query.filter(Product.color == filters["color"])
    if filters.get("colors"):
        query = query.filter(Product.color.in_(filters["colors"]))
    if filters.get("cpu"):
        value = f"%{filters['cpu']}%"
        query = query.filter(or_(Product.cpu.ilike(value), Product.name.ilike(value)))
    if filters.get("gpu"):
        value = f"%{filters['gpu']}%"
        query = query.filter(or_(Product.gpu.ilike(value), Product.name.ilike(value)))
    if filters.get("ram"):
        query = query.filter(Product.ram.ilike(f"%{filters['ram']}%"))
    if filters.get("storage"):
        query = query.filter(Product.storage.ilike(f"%{filters['storage']}%"))
    if filters.get("name"):
        query = query.filter(Product.name.ilike(f"%{filters['name']}%"))
    return query.distinct()


def find_products(db: Session, message: str, limit: int = 8) -> tuple[list[Product], dict]:
    filters = parse_product_filters(message)
    query = filter_products(db, filters)
    if not filters:
        keywords = [word for word in normalize_text(message).split() if len(word) >= 3]
        clauses = []
        for word in keywords[:5]:
            value = f"%{word}%"
            clauses.extend([Product.name.ilike(value), Product.detail.ilike(value)])
        if clauses:
            query = query.filter(or_(*clauses))
    return query.order_by(Product.price).limit(limit).all(), filters


def should_inherit_context_filters(message: str, filters: dict) -> bool:
    if not filters or filters.get("category_slug"):
        return False
    normalized = normalize_text(message)
    words = [word for word in normalized.split() if word]
    has_price_filter = any(key in filters for key in ["price_min", "price_max"])
    vague_words = any(word in normalized for word in ["san pham", "mon", "mau", "cai", "hang", "do"])
    return (has_price_filter and len(words) <= 6) or vague_words


def find_products_with_context(db: Session, request, message: str, limit: int = 8) -> tuple[list[Product], dict]:
    filters = parse_product_filters(message)
    last_filters = request.session.get("chatbot_last_filters") or {}
    if should_inherit_context_filters(message, filters) and last_filters.get("category_slug"):
        merged = dict(last_filters)
        merged.update(filters)
        query = filter_products(db, merged)
        return query.order_by(Product.price).limit(limit).all(), merged
    return find_products(db, message, limit)


def strip_cart_words(message: str) -> str:
    patterns = [
        r"(?i)\bthêm\b", r"(?i)\bthem\b", r"(?i)\bmua\b", r"(?i)\blấy\b", r"(?i)\blay\b",
        r"(?i)\bđặt\b", r"(?i)\bdat\b", r"(?i)\bchọn\b", r"(?i)\bchon\b",
        r"(?i)\bxóa\b", r"(?i)\bxoa\b", r"(?i)\bbỏ\b", r"(?i)\bbo\b", r"(?i)\bgỡ\b", r"(?i)\bgo\b",
        r"(?i)\badd to cart\b", r"(?i)\bcart\b", r"(?i)\bgiỏ hàng\b", r"(?i)\bgio hang\b",
        r"(?i)\bvào giỏ\b", r"(?i)\bvao gio\b", r"(?i)\bkhỏi giỏ\b", r"(?i)\bkhoi gio\b",
    ]
    cleaned = message
    for pattern in patterns:
        cleaned = re.sub(pattern, " ", cleaned)
    return re.sub(r"\s+", " ", cleaned).strip()


def parse_referenced_product_index(message: str) -> int | None:
    normalized = normalize_text(message)
    if any(keyword in normalized for keyword in ["dau tien", "sp dau", "san pham dau", "mon dau", "cai dau"]):
        return 0
    ordinal_words = {"mot": 0, "hai": 1, "ba": 2, "bon": 3, "tu": 3, "nam": 4}
    ordinal_match = re.search(r"(?:san pham|sp|do|mon|muc|cai|lua chon|option)\s*(?:thu\s*)?(mot|hai|ba|bon|tu|nam)", normalized)
    if ordinal_match:
        return ordinal_words.get(ordinal_match.group(1))
    match = re.search(r"(?:san pham|sp|do|mon|muc|cai|lua chon|option|so)?\s*so\s*(\d+)", normalized)
    if not match:
        match = re.search(r"(?:san pham|sp|do|mon|muc|cai|lua chon|option)\s*(?:thu\s*)?(\d+)", normalized)
    if not match:
        return None
    return max(int(match.group(1)) - 1, 0)


def is_previous_product_reference(message: str) -> bool:
    normalized = normalize_text(message)
    return any(
        keyword in normalized
        for keyword in [
            "san pham do", "san pham nay", "san pham vua roi", "sp nay", "sp do", "cai do", "cai nay",
            "may nay", "em nay", "con nay", "mau nay", "mau do", "nhu tren", "o tren",
        ]
    )


def has_cart_word(message: str) -> bool:
    normalized = clean_intent_text(message)
    return any(keyword in normalized for keyword in ["gio hang", "cart"])


def is_cart_view_request(message: str) -> bool:
    normalized = clean_intent_text(message)
    add_remove_words = {"them", "add", "mua", "lay", "dat", "chon", "xoa", "bo", "go", "remove", "delete"}
    if not has_cart_word(message) or any(word in normalized.split() for word in add_remove_words):
        return False
    return normalized in {"gio hang", "gio hang cua toi", "xem gio hang", "xem cart", "mo gio hang", "mo cart", "cart"} or any(
        phrase in normalized for phrase in ["xem gio hang", "mo gio hang", "mo cart", "xem cart", "kiem tra gio hang"]
    )


def is_remove_from_cart_request(message: str) -> bool:
    normalized = clean_intent_text(message)
    if any(phrase in normalized for phrase in ["xoa lich su", "xoa chat", "bo loc"]):
        return False
    words = normalized.split()
    has_remove = any(word in words for word in ["xoa", "bo", "go", "remove", "delete"])
    return has_remove and (has_cart_word(message) or normalized.startswith(("xoa ", "bo ", "go ")))


def is_add_to_cart_request(message: str) -> bool:
    normalized = normalize_text(message)
    if is_cart_view_request(message) or is_remove_from_cart_request(message):
        return False
    cart_keywords = ["them", "them vao gio", "bo vao gio", "dua vao gio", "cho vao gio", "vao gio hang", "add cart", "add to cart"]
    action_keywords = ["mua", "lay", "dat", "chon"]
    return any(keyword in normalized for keyword in cart_keywords) or (
        any(keyword in normalized for keyword in action_keywords)
        and (parse_referenced_product_index(message) is not None or is_previous_product_reference(message))
    )


def is_more_products_request(message: str) -> bool:
    normalized = normalize_text(message)
    return any(keyword in normalized for keyword in [
        "con san pham khac", "san pham khac", "mau khac", "may khac", "cai khac", "option khac",
        "lua chon khac", "con mau nao", "con cai nao", "con nua khong", "con nua ko", "xem them", "goi y khac",
    ])


def is_similar_products_request(message: str) -> bool:
    normalized = normalize_text(message)
    return any(keyword in normalized for keyword in [
        "san pham tuong tu", "mau tuong tu", "may tuong tu", "cung loai", "cung cau hinh", "gan giong", "tuong tu",
    ])


def is_context_detail_request(message: str) -> bool:
    normalized = normalize_text(message)
    detail_keywords = ["gia", "bao nhieu", "mau", "cpu", "gpu", "ram", "o cung", "luu tru", "cau hinh", "thong so", "ton kho", "con hang"]
    return any(keyword in normalized for keyword in detail_keywords) and (
        is_previous_product_reference(message) or parse_referenced_product_index(message) is not None
    )


def is_confirmation_yes(message: str) -> bool:
    return clean_intent_text(message) in {"dung", "dung roi", "chinh xac", "ok", "oke", "yes", "co", "phai", "phai roi", "xoa di"}


def is_confirmation_no(message: str) -> bool:
    return clean_intent_text(message) in {"khong", "khong dung", "khong phai", "ko", "ko dung", "ko phai", "sai", "nham"}


def find_products_by_name(db: Session, message: str, limit: int = 5) -> list[Product]:
    keyword = normalize_text(strip_cart_words(message))
    words = [word for word in keyword.split() if len(word) >= 2]
    products = db.query(Product).options(joinedload(Product.categories)).all()
    exact = [product for product in products if keyword and (normalize_text(product.name) in keyword or keyword in normalize_text(product.name))]
    if exact:
        return exact[:1]
    scored = []
    for product in products:
        haystack = normalize_text(" ".join(str(value or "") for value in [product.name, product.detail, product.cpu, product.gpu, product.ram, product.storage]))
        score = sum(1 for word in words if word in haystack)
        if keyword and keyword in haystack:
            score += 5
        if score:
            scored.append((score, product.price, product))
    scored.sort(key=lambda item: (-item[0], item[1]))
    return [product for _, _, product in scored[:limit]]


def select_product_for_cart(db: Session, request, message: str) -> Product | None:
    last_ids = request.session.get("chatbot_last_product_ids", [])
    ref_index = parse_referenced_product_index(message)
    if last_ids and ref_index is not None and ref_index < len(last_ids):
        return db.query(Product).filter(Product.id == last_ids[ref_index]).first()
    if last_ids and is_previous_product_reference(message):
        return db.query(Product).filter(Product.id == last_ids[0]).first()
    products = find_products_by_name(db, message, limit=1)
    return products[0] if products else None


def remember_products(request, products: list[Product], message: str | None = None, filters: dict | None = None, append_seen: bool = False):
    product_ids = [product.id for product in products]
    request.session["chatbot_last_product_ids"] = product_ids
    if append_seen:
        seen = set(request.session.get("chatbot_seen_product_ids", []))
        seen.update(product_ids)
        request.session["chatbot_seen_product_ids"] = list(seen)
    else:
        request.session["chatbot_seen_product_ids"] = product_ids
    if message is not None:
        request.session["chatbot_last_query"] = message
    if filters is not None:
        request.session["chatbot_last_filters"] = json.loads(json.dumps(filters, default=str))


def remember_added_product(request, product: Product):
    request.session["chatbot_last_added_product_id"] = product.id
    request.session["chatbot_last_product_ids"] = [product.id]


def get_cart_items_for_request(db: Session, request) -> tuple[Order | None, list]:
    return get_cart(db, request, get_current_user(request, db))


def add_product_to_cart(db: Session, request, product: Product):
    update_cart_item(db, request, product, "add", get_current_user(request, db))
    order, _ = get_cart_items_for_request(db, request)
    remember_added_product(request, product)
    return order


def format_cart_reply(db: Session, request) -> str:
    order, items = get_cart_items_for_request(db, request)
    if not order or not items:
        return "Giỏ hàng của bạn đang trống.\n\n[Xem giỏ hàng](/cart/)"
    rows = [f"{index}. **{item.product.name}** x {item.quantity} - {fmt_price(item.get_total)}đ" for index, item in enumerate(items, 1)]
    return (
        "Giỏ hàng hiện tại của bạn:\n\n"
        f"{chr(10).join(rows)}\n\n"
        f"- Tổng số lượng: {order.get_cart_items}\n"
        f"- Tổng tạm tính: {fmt_price(order.get_cart_total)}đ\n\n"
        "[Mở giỏ hàng](/cart/) | [Thanh toán](/checkout/)"
    )


def score_product_name(query: str, product: Product) -> int:
    keyword = normalize_text(query)
    words = [word for word in keyword.split() if len(word) >= 2]
    haystack = normalize_text(product.name)
    score = sum(1 for word in words if word in haystack)
    if keyword and keyword in haystack:
        score += 10
    if haystack and haystack in keyword:
        score += 12
    return score


def find_cart_items_by_name(db: Session, request, message: str) -> list[OrderItem]:
    _, items = get_cart_items_for_request(db, request)
    keyword = strip_cart_words(message)
    scored = []
    for item in items:
        score = score_product_name(keyword, item.product)
        if score:
            scored.append((score, item.product.price, item))
    scored.sort(key=lambda entry: (-entry[0], entry[1]))
    return [item for _, _, item in scored]


def clear_cart_confirmation(request):
    request.session.pop("chatbot_pending_cart_action", None)


def set_cart_confirmation(request, action: str, items: list[OrderItem], index: int = 0):
    request.session["chatbot_pending_cart_action"] = {
        "action": action,
        "item_ids": [item.id for item in items],
        "product_ids": [item.product.id for item in items if item.product],
        "index": index,
    }


def get_pending_cart_confirmation(db: Session, request):
    pending = request.session.get("chatbot_pending_cart_action") or {}
    item_ids = pending.get("item_ids") or []
    user = get_current_user(request, db)
    if user:
        items = db.query(OrderItem).options(joinedload(OrderItem.product)).filter(OrderItem.id.in_(item_ids), OrderItem.quantity > 0).all() if item_ids else []
        item_map = {item.id: item for item in items}
        ordered = [item_map[item_id] for item_id in item_ids if item_id in item_map]
    else:
        product_ids = pending.get("product_ids") or item_ids
        _, guest_items = get_cart_items_for_request(db, request)
        item_map = {item.product.id: item for item in guest_items if item.product}
        ordered = [item_map[product_id] for product_id in product_ids if product_id in item_map]
    if not pending or not ordered:
        clear_cart_confirmation(request)
        return None, [], 0
    return pending.get("action"), ordered, int(pending.get("index") or 0)


def build_confirm_remove_reply(request, items: list[OrderItem], index: int = 0) -> str:
    if not items:
        clear_cart_confirmation(request)
        return "Mình chưa tìm thấy sản phẩm đó trong giỏ hàng của bạn."
    index = min(max(index, 0), len(items) - 1)
    set_cart_confirmation(request, "remove", items, index)
    product = items[index].product
    extra = ""
    if len(items) > 1:
        extra = f"\n\nMình tìm thấy {len(items)} sản phẩm gần giống trong giỏ. Nếu không phải, bạn nhắn **không phải** để mình chuyển sang sản phẩm khác."
    return f"Bạn muốn xóa **{product.name}** khỏi giỏ hàng đúng không?\n\nTrả lời **đúng** để xóa, hoặc **không phải** nếu mình chọn nhầm.{extra}"


def remove_cart_item(db: Session, request, item: OrderItem) -> str:
    product = item.product
    update_cart_item(db, request, product, "remove", get_current_user(request, db))
    clear_cart_confirmation(request)
    order, _ = get_cart_items_for_request(db, request)
    total_items = order.get_cart_items if order else 0
    total_amount = fmt_price(order.get_cart_total) if order else "0"
    return f"Đã xóa **{product.name}** khỏi giỏ hàng.\n\n- Số lượng còn lại: {total_items}\n- Tổng tạm tính: {total_amount}đ\n\n[Xem giỏ hàng](/cart/)"


def handle_pending_cart_confirmation(db: Session, request, message: str) -> str | None:
    action, items, index = get_pending_cart_confirmation(db, request)
    if action != "remove":
        return None
    if is_confirmation_yes(message):
        return remove_cart_item(db, request, items[index])
    if is_confirmation_no(message):
        next_index = index + 1
        if next_index < len(items):
            return build_confirm_remove_reply(request, items, next_index)
        clear_cart_confirmation(request)
        return "Mình đã hết sản phẩm gần giống trong giỏ hàng. Bạn nhắn lại tên sản phẩm muốn xóa nhé."
    replacement_items = find_cart_items_by_name(db, request, message)
    if replacement_items:
        return build_confirm_remove_reply(request, replacement_items)
    return None


def build_remove_from_cart_reply(db: Session, request, message: str) -> str:
    _, items = get_cart_items_for_request(db, request)
    if not items:
        clear_cart_confirmation(request)
        return "Giỏ hàng của bạn đang trống, nên chưa có sản phẩm để xóa."
    ref_index = parse_referenced_product_index(message)
    if ref_index is not None and ref_index < len(items):
        return build_confirm_remove_reply(request, [items[ref_index]])
    matched = find_cart_items_by_name(db, request, message)
    if not matched:
        clear_cart_confirmation(request)
        return "Mình chưa tìm thấy sản phẩm đó trong giỏ hàng. Bạn có thể nhắn **xem giỏ hàng** để xem đúng tên sản phẩm đang có."
    return build_confirm_remove_reply(request, matched)


def build_add_to_cart_reply(db: Session, request, message: str) -> str:
    product = select_product_for_cart(db, request, message)
    if not product:
        return "Mình chưa tìm thấy sản phẩm bạn muốn thêm vào giỏ. Bạn có thể nói rõ hơn, ví dụ: **thêm sản phẩm số 1 vào giỏ hàng**."
    order = add_product_to_cart(db, request, product)
    return (
        f"Đã thêm **{product.name}** vào giỏ hàng.\n\n"
        f"- Số lượng trong giỏ: {order.get_cart_items}\n"
        f"- Tổng tạm tính: {fmt_price(order.get_cart_total)}đ\n\n"
        f"[Xem giỏ hàng](/cart/) | [Xem sản phẩm](/detail/?id={product.id})"
    )


def get_context_product(db: Session, request) -> Product | None:
    product_id = request.session.get("chatbot_last_added_product_id")
    if product_id:
        product = db.query(Product).filter(Product.id == product_id).first()
        if product:
            return product
    last_ids = request.session.get("chatbot_last_product_ids", [])
    if last_ids:
        return db.query(Product).filter(Product.id == last_ids[0]).first()
    return None


def build_context_detail_reply(db: Session, request, message: str) -> str:
    product = select_product_for_cart(db, request, message) or get_context_product(db, request)
    if not product:
        return "Mình chưa xác định được bạn đang hỏi sản phẩm nào. Bạn có thể nhắn tên sản phẩm hoặc chọn **sản phẩm số 1** nhé."
    specs = [
        f"CPU: {product.cpu}" if product.cpu else "",
        f"GPU: {product.gpu}" if product.gpu else "",
        f"RAM: {product.ram}" if product.ram else "",
        f"Lưu trữ: {product.storage}" if product.storage else "",
        f"Màu: {color_display(product.color)}" if product.color else "",
        f"Tồn kho: {product.stock}",
    ]
    specs = [item for item in specs if item]
    remember_products(request, [product], filters={"detail_product": product.id})
    return (
        f"Thông tin **{product.name}**:\n\n"
        f"<!--PRODUCT:{product.id}-->\n"
        f"- Giá: {fmt_price(product.price)}đ\n"
        f"- Danh mục: {product_categories(product)}\n"
        f"- {' | '.join(specs)}\n"
        "Nếu muốn mua, bạn nhắn **thêm sản phẩm này vào giỏ hàng**."
    )


def build_more_products_reply(db: Session, request, message: str) -> str:
    last_query = request.session.get("chatbot_last_query")
    filters = parse_product_filters(message) or request.session.get("chatbot_last_filters") or {}
    seen_ids = request.session.get("chatbot_seen_product_ids", [])
    if not last_query and not filters:
        return "Bạn muốn mình tìm thêm theo tiêu chí nào ạ? Ví dụ: **laptop dưới 15 triệu** hoặc **điện thoại tầm 5 triệu**."
    products = filter_products(db, filters).order_by(Product.price).limit(30).all() if filters else []
    if not products and last_query:
        products, filters = find_products(db, last_query, limit=30)
    other = [product for product in products if product.id not in seen_ids][:5]
    if not other:
        return "Hiện mình chưa thấy thêm sản phẩm khác khớp đúng tiêu chí vừa rồi. Bạn có thể nới điều kiện một chút nhé."
    remember_products(request, other, message=message or last_query, filters=filters, append_seen=True)
    return f"Mình tìm thêm được vài lựa chọn khác:\n\n{format_products_for_response(other)}\n\nBạn có thể nhắn **thêm sản phẩm số 1 vào giỏ hàng** nếu muốn chọn mẫu đầu tiên."


def build_similar_products_reply(db: Session, request) -> str:
    product = get_context_product(db, request)
    if not product:
        return "Bạn muốn tìm sản phẩm tương tự với mẫu nào ạ? Bạn có thể gửi tên sản phẩm hoặc hỏi trước như **laptop dưới 15 triệu**."
    category_ids = [category.id for category in product.categories]
    query = db.query(Product).options(joinedload(Product.categories)).filter(Product.id != product.id)
    if category_ids:
        query = query.join(Product.categories).filter(Category.id.in_(category_ids))
    lower = Decimal(str(product.price)) * Decimal("0.7")
    upper = Decimal(str(product.price)) * Decimal("1.3")
    products = query.filter(Product.price >= lower, Product.price <= upper).distinct().order_by(Product.price).limit(5).all()
    if not products:
        products = query.distinct().order_by(Product.price).limit(5).all()
    if not products:
        return f"Mình chưa thấy sản phẩm tương tự với **{product.name}** trong kho hiện tại."
    remember_products(request, products, filters={"similar_to": product.id})
    return f"Các sản phẩm tương tự **{product.name}**:\n\n{format_products_for_response(products)}\n\nBạn có thể nhắn **lấy số 1** để mình thêm vào giỏ."


def format_products_for_response(products: list[Product]) -> str:
    if not products:
        return "Không tìm thấy sản phẩm phù hợp."
    rows = []
    for index, product in enumerate(products, 1):
        specs = [
            f"CPU: {product.cpu}" if product.cpu else "",
            f"GPU: {product.gpu}" if product.gpu else "",
            f"RAM: {product.ram}" if product.ram else "",
            f"Lưu trữ: {product.storage}" if product.storage else "",
            f"Màu: {color_display(product.color)}" if product.color else "",
            f"Tồn kho: {product.stock}",
        ]
        specs = [item for item in specs if item]
        rows.append(
            f"{index}. {product.name}\n"
            f"<!--PRODUCT:{product.id}-->\n"
            f"- Giá: {fmt_price(product.price)}đ\n"
            f"- Danh mục: {product_categories(product)}\n"
            f"- Thông số: {' | '.join(specs)}"
        )
    return "\n\n".join(rows)


def ensure_product_markers(reply: str, products: list[Product]) -> str:
    reply = DETAIL_MARKDOWN_LINK_RE.sub("", reply)
    existing_ids = {int(match.group(1)) for match in PRODUCT_MARKER_RE.finditer(reply)}
    for product in products:
        if product.id in existing_ids:
            continue
        marker = f"<!--PRODUCT:{product.id}-->"
        pattern = re.compile(re.escape(product.name), re.IGNORECASE)
        if pattern.search(reply):
            reply = pattern.sub(lambda match: f"{match.group(0)}\n{marker}", reply, count=1)
        else:
            reply = f"{reply}\n\n{marker}"
    return reply


def get_recent_history(db: Session, request, limit: int = 5) -> str:
    user = get_current_user(request, db)
    if user:
        history = db.query(ChatHistory).filter(ChatHistory.user_id == user.id).order_by(ChatHistory.created_at.desc()).limit(limit).all()
        lines = [f"Khách: {item.message}\nBot: {item.reply}" for item in reversed(history)]
    else:
        session_history = request.session.get("chatbot_recent_history", [])[-limit:]
        lines = [f"Khách: {item['message']}\nBot: {item['reply']}" for item in session_history]
    return "\n\n".join(lines) if lines else "Chưa có lịch sử hội thoại."


def record_chat_history(db: Session, request, message: str, reply: str):
    history = request.session.get("chatbot_recent_history", [])
    history.append({"message": message, "reply": reply})
    request.session["chatbot_recent_history"] = history[-20:]
    user = get_current_user(request, db)
    if user:
        db.add(ChatHistory(user_id=user.id, message=message, reply=reply))
        db.commit()


def get_chat_history_payload(db: Session, request, limit: int = 30) -> list[dict]:
    user = get_current_user(request, db)
    if user:
        rows = (
            db.query(ChatHistory)
            .filter(ChatHistory.user_id == user.id)
            .order_by(ChatHistory.created_at.desc())
            .limit(limit)
            .all()
        )
        messages = []
        for item in reversed(rows):
            messages.append({"role": "user", "content": item.message})
            messages.append({"role": "bot", "content": item.reply})
        return messages

    session_history = request.session.get("chatbot_recent_history", [])[-limit:]
    messages = []
    for item in session_history:
        messages.append({"role": "user", "content": item.get("message", "")})
        messages.append({"role": "bot", "content": item.get("reply", "")})
    return messages


def build_fallback_reply(products: list[Product], filters: dict) -> str:
    if not products:
        return "Mình chưa tìm thấy sản phẩm khớp chính xác với yêu cầu này. Bạn có thể thử nới khoảng giá hoặc bỏ bớt điều kiện CPU/GPU/RAM nhé."
    return f"Mình tìm thấy vài lựa chọn phù hợp:\n\n{format_products_for_response(products)}"


def build_system_prompt(db: Session, request, products: list[Product], filters: dict) -> str:
    return f"""
Bạn là AI tư vấn bán hàng của Đà Nẵng Store - Tech & Gadgets.

Thông tin cửa hàng:
- Hotline: 0905 123 456
- Địa chỉ: 123 Nguyễn Văn Linh, Đà Nẵng
- Bảo hành 12 tháng, đổi trả 7 ngày, miễn phí ship đơn trên 1 triệu.

Bộ lọc đã trích xuất từ câu hỏi khách:
{json.dumps(filters, ensure_ascii=False, default=str)}

Lịch sử hội thoại gần đây:
{get_recent_history(db, request)}

Danh sách sản phẩm đã được truy vấn từ database:
{format_products_for_response(products)}

Quy tắc trả lời:
- Chỉ tư vấn dựa trên danh sách sản phẩm ở trên.
- Không bịa thêm sản phẩm ngoài database.
- Giữ marker ẩn <!--PRODUCT:X--> ngay sau tên từng sản phẩm được đề xuất.
- Nếu không có sản phẩm phù hợp, nói rõ và gợi ý khách nới tiêu chí.
- Trả lời bằng tiếng Việt, ngắn gọn, thân thiện.
"""


def clear_history(request):
    for key in [
        "chatbot_recent_history",
        "chatbot_last_product_ids",
        "chatbot_seen_product_ids",
        "chatbot_last_query",
        "chatbot_last_filters",
        "chatbot_last_added_product_id",
        "chatbot_pending_cart_action",
        "chat_history",
    ]:
        request.session.pop(key, None)


def get_product_previews(db: Session, raw_ids: str) -> list[dict]:
    ids = []
    for raw_id in raw_ids.split(","):
        try:
            ids.append(int(raw_id))
        except ValueError:
            continue
    if not ids:
        return []
    products = db.query(Product).filter(Product.id.in_(ids)).all()
    product_map = {product.id: product for product in products}
    return [
        {
            "id": product.id,
            "name": product.name,
            "price": f"{fmt_price(product.price)}đ",
            "image": product.ImageURL,
            "url": f"/detail/?id={product.id}",
        }
        for product_id in ids
        if (product := product_map.get(product_id))
    ]
