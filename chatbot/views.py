import json
import re
import unicodedata
from decimal import Decimal

from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt
from dotenv import load_dotenv

from app.models import Order, OrderItem, Product
from chatbot.ai_client import create_chat_completion, get_ai_settings
from chatbot.models import ChatHistory


load_dotenv()


PRICE_UNIT = Decimal("1000000")


CATEGORY_SLUGS = {"laptop", "dien-thoai", "linh-kien-pc", "phu-kien"}
INTENTS = {"search", "more", "similar", "detail", "add_to_cart", "store_info", "smalltalk", "unknown"}


def normalize_text(value: str) -> str:
    value = unicodedata.normalize("NFD", value or "")
    value = "".join(ch for ch in value if unicodedata.category(ch) != "Mn")
    return value.lower()


def extract_json_object(text: str) -> dict:
    if not text:
        return {}

    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json)?", "", cleaned, flags=re.IGNORECASE).strip()
    cleaned = re.sub(r"```$", "", cleaned).strip()

    try:
        data = json.loads(cleaned)
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        pass

    match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
    if not match:
        return {}

    try:
        data = json.loads(match.group(0))
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        return {}


def normalize_category_slug(value: str | None) -> str | None:
    normalized = normalize_text(value or "").replace("_", "-").replace(" ", "-")
    aliases = {
        "phone": "dien-thoai",
        "smartphone": "dien-thoai",
        "dien-thoai": "dien-thoai",
        "dt": "dien-thoai",
        "computer": "laptop",
        "may-tinh": "laptop",
        "notebook": "laptop",
        "pc-component": "linh-kien-pc",
        "linh-kien": "linh-kien-pc",
        "component": "linh-kien-pc",
        "accessory": "phu-kien",
        "phu-kien": "phu-kien",
    }
    normalized = aliases.get(normalized, normalized)
    return normalized if normalized in CATEGORY_SLUGS else None


def normalize_ai_filters(raw_filters: dict) -> dict:
    if not isinstance(raw_filters, dict):
        return {}

    filters = {}
    category_slug = normalize_category_slug(raw_filters.get("category_slug") or raw_filters.get("category"))
    if category_slug:
        filters["category_slug"] = category_slug

    exclude_category_slug = normalize_category_slug(raw_filters.get("exclude_category_slug") or raw_filters.get("exclude_category"))
    if exclude_category_slug:
        filters["exclude_category_slug"] = exclude_category_slug

    for key in ["price_min", "price_max"]:
        value = raw_filters.get(key)
        if value in (None, "", []):
            continue
        try:
            filters[key] = Decimal(str(value))
        except Exception:
            pass

    for key in ["cpu", "gpu", "ram", "storage", "color"]:
        value = raw_filters.get(key)
        if isinstance(value, str) and value.strip():
            filters[key] = value.strip()

    colors = raw_filters.get("colors")
    if isinstance(colors, list):
        filters["colors"] = [str(color).strip() for color in colors if str(color).strip()]

    return filters


def get_special_reply(message: str) -> str | None:
    normalized = normalize_text(message).strip()
    normalized = re.sub(r"[^\w\s]", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()

    greetings = {
        "hi",
        "hello",
        "hey",
        "chao",
        "xin chao",
        "chao shop",
        "shop oi",
        "alo",
        "alo shop",
    }
    thanks = {"cam on", "thanks", "thank you", "tks", "ok cam on", "cam on shop"}
    goodbyes = {"bye", "tam biet", "hen gap lai", "chao tam biet"}

    if normalized in greetings:
        return (
            "Xin chào! Mình là trợ lý của Đà Nẵng Store. "
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
            "Bạn có thể hỏi mình theo kiểu: "
            "\"laptop dưới 15 triệu\", \"điện thoại tầm 5 triệu\", "
            "\"máy core i7 card RTX\", hoặc \"MacBook màu xám không gian\"."
        )

    return None


def get_session_context(request) -> dict:
    last_ids = request.session.get("chatbot_last_product_ids", [])
    products = Product.objects.filter(id__in=last_ids).prefetch_related("category")
    product_map = {product.id: product for product in products}
    ordered_products = [product_map[product_id] for product_id in last_ids if product_id in product_map]

    return {
        "last_query": request.session.get("chatbot_last_query", ""),
        "last_filters": request.session.get("chatbot_last_filters") or {},
        "last_products": [
            {
                "id": product.id,
                "name": product.name,
                "price": int(product.price),
                "category": ", ".join(category.name for category in product.category.all()),
            }
            for product in ordered_products[:5]
        ],
        "last_added_product_id": request.session.get("chatbot_last_added_product_id"),
    }


def get_ai_intent(request, message: str) -> dict:
    ai_settings = get_ai_settings()
    if not ai_settings["api_key"]:
        return {}

    context = get_session_context(request)
    system_prompt = """
Bạn là bộ phân tích intent cho chatbot bán đồ công nghệ Đà Nẵng Store.
Chỉ trả về JSON hợp lệ, không giải thích, không markdown.

Schema:
{
  "intent": "search|more|similar|detail|add_to_cart|store_info|smalltalk|unknown",
  "filters": {
    "category_slug": "laptop|dien-thoai|linh-kien-pc|phu-kien|null",
    "exclude_category_slug": "laptop|dien-thoai|linh-kien-pc|phu-kien|null",
    "price_min": number|null,
    "price_max": number|null,
    "cpu": string|null,
    "gpu": string|null,
    "ram": string|null,
    "storage": string|null,
    "color": string|null
  },
  "reference_index": number|null,
  "reference_previous": boolean,
  "needs_context": boolean
}

Quy ước:
- Giá dùng đơn vị VND. "5tr", "5 triệu", "5 củ" = 5000000.
- "dưới 5tr", "duoi 5 tr", "dung cu 5 tr" nghĩa là price_max 5000000.
- "tầm/khoảng 5tr" nghĩa là price_min 4000000 và price_max 6000000.
- Nếu câu rút gọn như "món khác dưới 5tr", giữ category_slug từ last_filters nếu có.
- "sản phẩm khác", "mẫu khác", "còn cái nào không" là intent more.
- "không phải điện thoại/laptop/phụ kiện/linh kiện nữa" thì đặt exclude_category_slug tương ứng và bỏ category_slug đó.
- "tương tự", "cùng loại", "giống mẫu này" là intent similar.
- "thêm/lấy/mua/chọn sản phẩm số 1/cái này/vào giỏ" là intent add_to_cart.
- reference_index là chỉ số 0-based nếu người dùng nói số thứ tự.
"""

    user_prompt = json.dumps(
        {
            "message": message,
            "context": context,
        },
        ensure_ascii=False,
        default=str,
    )

    try:
        raw_reply = create_chat_completion(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.1,
            max_tokens=500,
        )
    except Exception as exc:
        print(f"{ai_settings['provider_name']} Intent Error: {type(exc).__name__} - {exc}")
        return {}

    intent = extract_json_object(raw_reply)
    if intent.get("intent") not in INTENTS:
        intent["intent"] = "unknown"
    intent["filters"] = normalize_ai_filters(intent.get("filters") or {})
    return intent


def get_ai_reply(request, message: str, products: list, filters: dict, fallback_reply: str) -> str:
    ai_settings = get_ai_settings()
    if not ai_settings["api_key"]:
        return fallback_reply

    try:
        return create_chat_completion(
            messages=[
                {"role": "system", "content": build_system_prompt(request, products, filters)},
                {"role": "user", "content": message},
            ],
            temperature=0.65,
            max_tokens=1200,
        )
    except Exception as exc:
        print(f"{ai_settings['provider_name']} Reply Error: {type(exc).__name__} - {exc}")
        return fallback_reply


def is_add_to_cart_request(message: str) -> bool:
    normalized = normalize_text(message)
    cart_keywords = [
        "them",
        "them gio",
        "them vao gio",
        "them vao cart",
        "bo gio",
        "bo vao gio",
        "dua vao gio",
        "cho vao gio",
        "cho san pham vao gio",
        "cho cai nay vao gio",
        "cho mau nay vao gio",
        "vao gio hang",
        "gio hang",
        "add cart",
        "add to cart",
    ]
    action_keywords = ["mua", "lay", "dat", "chon"]
    return any(keyword in normalized for keyword in cart_keywords) or (
        any(keyword in normalized for keyword in action_keywords)
        and (parse_referenced_product_index(message) is not None or is_previous_product_reference(message))
    )


def is_more_products_request(message: str) -> bool:
    normalized = normalize_text(message)
    return any(
        keyword in normalized
        for keyword in [
            "con san pham khac",
            "san pham khac",
            "mau khac",
            "may khac",
            "cai khac",
            "option khac",
            "lua chon khac",
            "con mau nao",
            "con cai nao",
            "con nua khong",
            "con nua ko",
            "con hang khac",
            "xem them",
            "goi y khac",
            "khac khong",
            "khac ko",
            "the mon khac",
            "the mau khac",
            "doi mau khac",
            "doi san pham khac",
        ]
    )


def is_similar_products_request(message: str) -> bool:
    normalized = normalize_text(message)
    return any(
        keyword in normalized
        for keyword in [
            "san pham tuong tu",
            "mau tuong tu",
            "may tuong tu",
            "cai tuong tu",
            "hang tuong tu",
            "cung loai",
            "cung cau hinh",
            "cau hinh gan",
            "gan giong",
            "giong san pham",
            "lien quan",
            "tuong tu",
        ]
    )


def is_context_detail_request(message: str) -> bool:
    normalized = normalize_text(message)
    detail_keywords = [
        "gia",
        "bao nhieu",
        "mau",
        "cpu",
        "gpu",
        "ram",
        "o cung",
        "luu tru",
        "cau hinh",
        "thong so",
        "ton kho",
        "con hang",
        "het hang",
    ]
    return any(keyword in normalized for keyword in detail_keywords) and (
        is_previous_product_reference(message) or parse_referenced_product_index(message) is not None
    )


def strip_cart_words(message: str) -> str:
    normalized_original = message
    patterns = [
        r"(?i)\bthem\b",
        r"(?i)\bthêm\b",
        r"(?i)\bmua\b",
        r"(?i)\blay\b",
        r"(?i)\blấy\b",
        r"(?i)\bdat\b",
        r"(?i)\bđặt\b",
        r"(?i)\bchon\b",
        r"(?i)\bchọn\b",
        r"(?i)\badd to cart\b",
        r"(?i)\bvao gio hang\b",
        r"(?i)\bvào giỏ hàng\b",
        r"(?i)\bgio hang\b",
        r"(?i)\bgiỏ hàng\b",
        r"(?i)\bbo vao gio\b",
        r"(?i)\bcho vao gio\b",
    ]
    for pattern in patterns:
        normalized_original = re.sub(pattern, " ", normalized_original)
    return re.sub(r"\s+", " ", normalized_original).strip()


def parse_referenced_product_index(message: str) -> int | None:
    normalized = normalize_text(message)
    if any(keyword in normalized for keyword in ["dau tien", "sp dau", "san pham dau", "mon dau", "cai dau"]):
        return 0

    ordinal_words = {
        "mot": 0,
        "hai": 1,
        "ba": 2,
        "bon": 3,
        "tu": 3,
        "nam": 4,
    }
    ordinal_match = re.search(r"(?:san pham|sp|do|mon|muc|cai|lua chon|option)\s*(?:thu\s*)?(mot|hai|ba|bon|tu|nam)", normalized)
    if ordinal_match:
        return ordinal_words.get(ordinal_match.group(1))

    match = re.search(r"(?:san pham|sp|do|mon|muc|cai|lua chon|option|so)?\s*so\s*(\d+)", normalized)
    if not match:
        match = re.search(r"(?:san pham|sp|do|mon|muc|cai|lua chon|option)\s*(?:thu\s*)?(\d+)", normalized)
    if not match:
        return None

    try:
        return max(int(match.group(1)) - 1, 0)
    except ValueError:
        return None


def is_previous_product_reference(message: str) -> bool:
    normalized = normalize_text(message)
    return any(
        keyword in normalized
        for keyword in [
            "san pham do",
            "san pham nay",
            "san pham vao gio",
            "cho san pham vao gio",
            "them san pham vao gio",
            "san pham vua roi",
            "sp nay",
            "sp do",
            "cai do",
            "cai nay",
            "may nay",
            "em nay",
            "con nay",
            "mau nay",
            "mau do",
            "hang nay",
            "mat hang nay",
            "do do",
            "mon do",
            "mon nay",
            "option nay",
            "option do",
            "cau hinh nay",
            "lua chon vua roi",
            "nhu tren",
            "o tren",
            "san pham tren",
            "cai tren",
            "mau tren",
            "lua chon tren",
            "lua chon nay",
            "hang tren",
            "mat hang tren",
        ]
    )


def parse_price_filters(text: str) -> dict:
    filters = {}
    normalized = normalize_text(text)

    price_unit_pattern = r"(?:trieu|triệu|tr|m|cu|củ)"
    range_match = re.search(
        rf"(?:tu|khoang)\s*(\d+(?:[.,]\d+)?)\s*(?:den|-)\s*(\d+(?:[.,]\d+)?)\s*{price_unit_pattern}",
        normalized,
    )
    if range_match:
        low = Decimal(range_match.group(1).replace(",", ".")) * PRICE_UNIT
        high = Decimal(range_match.group(2).replace(",", ".")) * PRICE_UNIT
        filters["price_min"] = min(low, high)
        filters["price_max"] = max(low, high)
        return filters

    amount_match = re.search(rf"(\d+(?:[.,]\d+)?)\s*{price_unit_pattern}", normalized)
    amount = Decimal(amount_match.group(1).replace(",", ".")) * PRICE_UNIT if amount_match else None

    if amount is None:
        return filters

    if any(word in normalized for word in ["duoi", "dưới", "dung cu", "duoi cu", "re hon", "nho hon", "<"]):
        filters["price_max"] = amount
    elif any(word in normalized for word in ["tren", "trên", "cao hon", "lon hon", ">"]):
        filters["price_min"] = amount
    elif any(word in normalized for word in ["tam", "tầm", "khoang", "gan", "khoảng"]):
        filters["price_min"] = amount * Decimal("0.8")
        filters["price_max"] = amount * Decimal("1.2")

    return filters


def parse_product_filters(message: str) -> dict:
    normalized = normalize_text(message)
    filters = parse_price_filters(message)

    categories = {
        "laptop": ["laptop", "may tinh", "may tinh xach tay", "notebook", "macbook"],
        "dien-thoai": ["dien thoai", "dt", "smartphone", "phone", "iphone", "samsung", "xiaomi"],
        "linh-kien-pc": ["linh kien", "cpu", "gpu", "card", "card do hoa", "ram", "pc"],
        "phu-kien": ["phu kien", "chuot", "ban phim", "tai nghe"],
    }
    for slug, keywords in categories.items():
        negated = any(
            f"khong phai {keyword}" in normalized
            or f"khong {keyword}" in normalized
            or f"ko phai {keyword}" in normalized
            or f"ko {keyword}" in normalized
            for keyword in keywords
        )
        if negated:
            filters["exclude_category_slug"] = slug
            break

        if any(keyword in normalized for keyword in keywords):
            filters["category_slug"] = slug
            break

    colors = [
        ("space_gray", ["xam khong gian", "space gray", "space_gray"]),
        ("black", ["den", "black"]),
        ("white", ["trang", "white"]),
        ("silver", ["bac", "silver"]),
        ("gold", ["vang kim", "gold"]),
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

    ram_match = re.search(r"\b(8|12|16|24|32|64)\s*gb\s*(?:ram)?\b", normalized)
    if ram_match:
        filters["ram"] = f"{ram_match.group(1)}GB"

    storage_match = re.search(r"\b(128|256|512)\s*gb|(\d+)\s*tb\b", normalized)
    if storage_match:
        filters["storage"] = storage_match.group(0).upper().replace(" ", "")

    return filters


def filter_products(filters: dict):
    products = Product.objects.prefetch_related("category").all()

    if filters.get("price_min"):
        products = products.filter(price__gte=Decimal(str(filters["price_min"])))
    if filters.get("price_max"):
        products = products.filter(price__lte=Decimal(str(filters["price_max"])))
    if filters.get("category_slug"):
        products = products.filter(category__slug=filters["category_slug"])
    if filters.get("exclude_category_slug"):
        products = products.exclude(category__slug=filters["exclude_category_slug"])
    if filters.get("color"):
        products = products.filter(color=filters["color"])
    if filters.get("colors"):
        products = products.filter(color__in=filters["colors"])
    if filters.get("cpu"):
        products = products.filter(Q(cpu__icontains=filters["cpu"]) | Q(name__icontains=filters["cpu"]))
    if filters.get("gpu"):
        products = products.filter(Q(gpu__icontains=filters["gpu"]) | Q(name__icontains=filters["gpu"]))
    if filters.get("ram"):
        products = products.filter(ram__icontains=filters["ram"])
    if filters.get("storage"):
        products = products.filter(storage__icontains=filters["storage"])

    return products.distinct()


def find_products(message: str, limit: int = 8) -> tuple[list, dict]:
    filters = parse_product_filters(message)
    products = filter_products(filters)

    if not filters:
        keywords = [word for word in normalize_text(message).split() if len(word) >= 3]
        query = Q()
        for word in keywords[:5]:
            query |= Q(name__icontains=word) | Q(detail__icontains=word)
        if query:
            products = products.filter(query)

    return list(products.distinct().order_by("price")[:limit]), filters


def should_inherit_context_filters(message: str, filters: dict) -> bool:
    if not filters or filters.get("category_slug"):
        return False

    normalized = normalize_text(message)
    words = [word for word in normalized.split() if word]
    has_price_filter = any(key in filters for key in ["price_min", "price_max"])
    short_price_query = has_price_filter and len(words) <= 6
    vague_product_words = any(word in normalized for word in ["san pham", "mon", "mau", "cai", "hang", "do"])
    return short_price_query or vague_product_words


def find_products_with_context(request, message: str, limit: int = 8, ai_intent: dict | None = None) -> tuple[list, dict]:
    filters = merge_rule_and_ai_filters(request, message, ai_intent)
    last_filters = request.session.get("chatbot_last_filters") or {}

    if should_inherit_context_filters(message, filters) and last_filters.get("category_slug"):
        merged_filters = dict(last_filters)
        merged_filters.update(filters)
        filters = merged_filters
        products = filter_products(filters)

        return list(products.order_by("price")[:limit]), filters

    return find_products(message, limit=limit)


def find_products_by_name(message: str, limit: int = 5) -> list:
    keyword = normalize_text(strip_cart_words(message))
    words = [word for word in keyword.split() if len(word) >= 2]
    products = list(Product.objects.prefetch_related("category").all())

    exact_matches = [
        product
        for product in products
        if normalize_text(product.name) in keyword or keyword in normalize_text(product.name)
    ]
    if exact_matches:
        return exact_matches[:1]

    scored = []
    for product in products:
        haystack = normalize_text(
            " ".join(
                str(value or "")
                for value in [product.name, product.detail, product.cpu, product.gpu, product.ram, product.storage]
            )
        )
        score = sum(1 for word in words if word in haystack)
        if keyword and keyword in haystack:
            score += 5
        if score:
            scored.append((score, product.price, product))

    scored.sort(key=lambda item: (-item[0], item[1]))
    return [product for score, price, product in scored[:limit]]


def select_product_for_cart(request, message: str):
    last_ids = request.session.get("chatbot_last_product_ids", [])
    ref_index = parse_referenced_product_index(message)

    if last_ids and ref_index is not None and ref_index < len(last_ids):
        return Product.objects.filter(id=last_ids[ref_index]).first()

    if last_ids and is_previous_product_reference(message):
        return Product.objects.filter(id=last_ids[0]).first()

    products = find_products_by_name(message, limit=1)
    return products[0] if products else None


def remember_products(request, products: list, message: str | None = None, filters: dict | None = None, append_seen: bool = False):
    product_ids = [product.id for product in products]
    request.session["chatbot_last_product_ids"] = product_ids

    if append_seen:
        seen_ids = set(request.session.get("chatbot_seen_product_ids", []))
        seen_ids.update(product_ids)
        request.session["chatbot_seen_product_ids"] = list(seen_ids)
    else:
        request.session["chatbot_seen_product_ids"] = product_ids

    if message is not None:
        request.session["chatbot_last_query"] = message
    if filters is not None:
        request.session["chatbot_last_filters"] = json.loads(json.dumps(filters, default=str))

    request.session.modified = True


def remember_added_product(request, product):
    request.session["chatbot_last_added_product_id"] = product.id
    request.session["chatbot_last_product_ids"] = [product.id]
    request.session.modified = True


def merge_context_filters(request, message: str) -> dict:
    last_filters = request.session.get("chatbot_last_filters") or {}
    current_filters = parse_product_filters(message)
    merged = dict(last_filters)

    for key, value in current_filters.items():
        if value not in (None, "", [], {}):
            merged[key] = value

    return merged


def merge_rule_and_ai_filters(request, message: str, ai_intent: dict | None = None) -> dict:
    last_filters = request.session.get("chatbot_last_filters") or {}
    filters = dict(last_filters) if (ai_intent or {}).get("intent") == "more" else {}
    ai_filters = normalize_ai_filters((ai_intent or {}).get("filters") or {})
    rule_filters = parse_product_filters(message)
    filters.update(ai_filters)
    filters.update(rule_filters)

    if filters.get("exclude_category_slug") and filters.get("category_slug") == filters["exclude_category_slug"]:
        filters.pop("category_slug", None)

    if should_inherit_context_filters(message, filters) and not filters.get("exclude_category_slug"):
        if last_filters.get("category_slug") and not filters.get("category_slug"):
            filters["category_slug"] = last_filters["category_slug"]

    return filters


def add_product_to_cart(request, product):
    if not request.user.is_authenticated:
        return None

    order, created = Order.objects.get_or_create(customer=request.user, complete=False)
    order_item, created = OrderItem.objects.get_or_create(order=order, product=product)
    order_item.quantity += 1
    order_item.save()
    remember_added_product(request, product)
    return order


def build_add_to_cart_reply(request, product) -> str:
    if not product:
        return (
            "Mình chưa tìm thấy sản phẩm bạn muốn thêm vào giỏ. "
            "Bạn có thể nói rõ hơn, ví dụ: **thêm sản phẩm số 1 vào giỏ hàng** hoặc **thêm Xiaomi Redmi Note 13 vào giỏ hàng**."
        )

    if not request.user.is_authenticated:
        return (
            f"Mình tìm thấy **{product.name}**, nhưng bạn cần đăng nhập trước khi thêm vào giỏ.\n\n"
            f"[Xem sản phẩm](/detail/?id={product.id}) | [Đăng nhập](/login/)"
        )

    order = add_product_to_cart(request, product)
    return (
        f"Đã thêm **{product.name}** vào giỏ hàng.\n\n"
        f"- Số lượng trong giỏ: {order.get_cart_items}\n"
        f"- Tổng tạm tính: {int(order.get_cart_total):,}đ\n".replace(",", ".")
        + f"\n[Xem giỏ hàng](/cart/) | [Xem sản phẩm](/detail/?id={product.id})"
    )


def get_context_product(request):
    product_id = request.session.get("chatbot_last_added_product_id")
    if product_id:
        product = Product.objects.filter(id=product_id).first()
        if product:
            return product

    last_ids = request.session.get("chatbot_last_product_ids", [])
    if last_ids:
        return Product.objects.filter(id=last_ids[0]).first()

    return None


def build_context_detail_reply(request, message: str) -> str:
    product = select_product_for_cart(request, message) or get_context_product(request)
    if not product:
        return "Mình chưa xác định được bạn đang hỏi sản phẩm nào. Bạn có thể nhắn tên sản phẩm hoặc chọn **sản phẩm số 1** nhé."

    price_vnd = f"{int(product.price):,}".replace(",", ".")
    categories = ", ".join(cat.name for cat in product.category.all()) or "Chưa phân loại"
    specs = [
        f"CPU: {product.cpu}" if product.cpu else "",
        f"GPU: {product.gpu}" if product.gpu else "",
        f"RAM: {product.ram}" if product.ram else "",
        f"Lưu trữ: {product.storage}" if product.storage else "",
        f"Màu: {product.get_color_display()}" if product.color else "",
        f"Tồn kho: {product.stock}",
    ]
    specs = [item for item in specs if item]
    remember_products(request, [product], filters={"detail_product": product.id})
    return (
        f"Thông tin **{product.name}**:\n\n"
        f"- Giá: {price_vnd}đ\n"
        f"- Danh mục: {categories}\n"
        f"- {' | '.join(specs)}\n"
        f"- [Xem chi tiết](/detail/?id={product.id})\n\n"
        "Nếu muốn mua, bạn nhắn **thêm sản phẩm này vào giỏ hàng**."
    )


def build_more_products_reply(request, message: str, ai_intent: dict | None = None) -> str:
    last_query = request.session.get("chatbot_last_query")
    filters = merge_rule_and_ai_filters(request, message, ai_intent) or merge_context_filters(request, message)
    seen_ids = request.session.get("chatbot_seen_product_ids", [])

    if not last_query and not filters:
        return (
            "Bạn muốn mình tìm thêm theo tiêu chí nào ạ? "
            "Ví dụ: **laptop dưới 15 triệu**, **điện thoại tầm 5 triệu**, hoặc **máy có RAM 16GB**."
        )

    products = list(filter_products(filters).order_by("price")[:30]) if filters else []
    if not products and last_query:
        products, filters = find_products(last_query, limit=30)

    other_products = [product for product in products if product.id not in seen_ids][:5]
    if not other_products and filters.get("price_min") and filters.get("price_max"):
        relaxed_filters = dict(filters)
        relaxed_filters.pop("price_min", None)
        products = list(filter_products(relaxed_filters).order_by("price")[:30])
        other_products = [product for product in products if product.id not in seen_ids][:5]
        if other_products:
            filters = relaxed_filters

    if not other_products and filters.get("exclude_category_slug"):
        relaxed_filters = {"exclude_category_slug": filters["exclude_category_slug"]}
        if filters.get("price_max"):
            relaxed_filters["price_max"] = filters["price_max"]
        products = list(filter_products(relaxed_filters).order_by("price")[:30])
        other_products = [product for product in products if product.id not in seen_ids][:5]
        if not other_products:
            relaxed_filters = {"exclude_category_slug": filters["exclude_category_slug"]}
            products = list(filter_products(relaxed_filters).order_by("price")[:30])
            other_products = [product for product in products if product.id not in seen_ids][:5]
        if other_products:
            filters = relaxed_filters

    if not other_products:
        direct_exclude = parse_product_filters(message).get("exclude_category_slug")
        if direct_exclude:
            relaxed_filters = {"exclude_category_slug": direct_exclude}
            products = list(filter_products(relaxed_filters).order_by("price")[:30])
            other_products = [product for product in products if product.id not in seen_ids][:5]
            if other_products:
                filters = relaxed_filters

    if not other_products:
        return (
            "Hiện mình chưa thấy thêm sản phẩm khác khớp đúng tiêu chí vừa rồi. "
            "Bạn có thể nới điều kiện một chút, ví dụ tăng khoảng giá hoặc bỏ bớt CPU/GPU/RAM."
        )

    remember_products(request, other_products, message=message or last_query, filters=filters, append_seen=True)
    return (
        "Mình tìm thêm được vài lựa chọn khác:\n\n"
        f"{format_products_for_response(other_products)}\n\n"
        "Bạn có thể nhắn **thêm sản phẩm số 1 vào giỏ hàng** nếu muốn chọn mẫu đầu tiên."
    )


def build_similar_products_reply(request) -> str:
    product = get_context_product(request)
    if not product:
        return (
            "Bạn muốn tìm sản phẩm tương tự với mẫu nào ạ? "
            "Bạn có thể gửi tên sản phẩm hoặc hỏi trước như **laptop dưới 15 triệu**."
        )

    category_ids = list(product.category.values_list("id", flat=True))
    similar_products = Product.objects.prefetch_related("category").exclude(id=product.id)
    if category_ids:
        similar_products = similar_products.filter(category__id__in=category_ids)

    lower_price = product.price * Decimal("0.7")
    upper_price = product.price * Decimal("1.3")
    price_close_products = list(
        similar_products.filter(price__gte=lower_price, price__lte=upper_price).distinct().order_by("price")[:5]
    )
    products = price_close_products or list(similar_products.distinct().order_by("price")[:5])

    if not products:
        return (
            f"Mình chưa thấy sản phẩm tương tự với **{product.name}** trong kho hiện tại. "
            "Bạn có thể thử tìm theo khoảng giá hoặc cấu hình khác."
        )

    remember_products(request, products, filters={"similar_to": product.id})
    return (
        f"Các sản phẩm tương tự **{product.name}**:\n\n"
        f"{format_products_for_response(products)}\n\n"
        "Bạn có thể nhắn **lấy số 1** hoặc **thêm mẫu này vào giỏ hàng** để mình thêm vào giỏ."
    )


def format_products_for_response(products: list) -> str:
    if not products:
        return "Không tìm thấy sản phẩm phù hợp."

    rows = []
    for index, product in enumerate(products, 1):
        price_vnd = f"{int(product.price):,}".replace(",", ".")
        categories = ", ".join(cat.name for cat in product.category.all()) or "Chưa phân loại"
        specs = [
            item
            for item in [
                f"CPU: {product.cpu}" if product.cpu else "",
                f"GPU: {product.gpu}" if product.gpu else "",
                f"RAM: {product.ram}" if product.ram else "",
                f"Lưu trữ: {product.storage}" if product.storage else "",
                f"Màu: {product.get_color_display()}" if product.color else "",
                f"Tồn kho: {product.stock}",
            ]
            if item
        ]
        rows.append(
            f"{index}. {product.name}\n"
            f"- Giá: {price_vnd}đ\n"
            f"- Danh mục: {categories}\n"
            f"- Thông số: {' | '.join(specs)}\n"
            f"- [Xem chi tiết](/detail/?id={product.id})"
        )

    return "\n\n".join(rows)


def get_recent_history(request, limit: int = 5) -> str:
    if not request.user.is_authenticated:
        return "Khách chưa đăng nhập, chưa có lịch sử hội thoại."

    history = ChatHistory.objects.filter(user=request.user).order_by("-created_at")[:limit]
    lines = []
    for item in reversed(history):
        lines.append(f"Khách: {item.message}\nBot: {item.reply}")

    return "\n\n".join(lines) if lines else "Chưa có lịch sử hội thoại."


def build_fallback_reply(products: list, filters: dict) -> str:
    if not products:
        return (
            "Mình chưa tìm thấy sản phẩm khớp chính xác với yêu cầu này. "
            "Bạn có thể thử nới khoảng giá hoặc bỏ bớt điều kiện CPU/GPU/RAM nhé."
        )

    return (
        "Mình tìm thấy vài lựa chọn phù hợp:\n\n"
        f"{format_products_for_response(products)}\n\n"
        "Bạn có thể bấm link chi tiết để xem thêm cấu hình và đặt hàng."
    )


def build_system_prompt(request, products: list, filters: dict) -> str:
    return f"""
Bạn là AI tư vấn bán hàng của Đà Nẵng Store - Tech & Gadgets.

Thông tin cửa hàng:
- Hotline: 0905 123 456
- Địa chỉ: 123 Nguyễn Văn Linh, Đà Nẵng
- Bảo hành 12 tháng, đổi trả 7 ngày, miễn phí ship đơn trên 1 triệu.

Bộ lọc đã trích xuất từ câu hỏi khách:
{json.dumps(filters, ensure_ascii=False, default=str)}

Lịch sử hội thoại gần đây:
{get_recent_history(request)}

Danh sách sản phẩm đã được truy vấn từ database:
{format_products_for_response(products)}

Quy tắc trả lời:
- Chỉ tư vấn dựa trên danh sách sản phẩm ở trên.
- Luôn kèm link /detail/?id=X cho sản phẩm được đề xuất.
- Nếu không có sản phẩm phù hợp, nói rõ và gợi ý khách nới tiêu chí.
- Trả lời bằng tiếng Việt, ngắn gọn, thân thiện, chuyên nghiệp.
"""


def chatbot_view(request):
    return render(request, "chatbot/chatbot.html")


@csrf_exempt
def chatbot_api(request):
    if request.method != "POST":
        return JsonResponse({"reply": "Phương thức không hợp lệ"}, status=400)

    try:
        data = json.loads(request.body)
        user_message = data.get("message", "").strip()
    except Exception:
        user_message = (request.POST.get("message") or "").strip()

    if not user_message:
        return JsonResponse({"reply": "Vui lòng nhập tin nhắn."})

    ai_intent = get_ai_intent(request, user_message)
    intent_name = ai_intent.get("intent")

    special_reply = get_special_reply(user_message)
    if special_reply and intent_name in (None, "", "smalltalk", "store_info", "unknown"):
        if request.user.is_authenticated:
            ChatHistory.objects.create(user=request.user, message=user_message, reply=special_reply)
        return JsonResponse({"reply": special_reply})

    if intent_name == "more" or is_more_products_request(user_message):
        reply = build_more_products_reply(request, user_message, ai_intent)
        if request.user.is_authenticated:
            ChatHistory.objects.create(user=request.user, message=user_message, reply=reply)
        return JsonResponse({"reply": reply})

    if intent_name == "similar" or is_similar_products_request(user_message):
        reply = build_similar_products_reply(request)
        if request.user.is_authenticated:
            ChatHistory.objects.create(user=request.user, message=user_message, reply=reply)
        return JsonResponse({"reply": reply})

    if intent_name == "detail" or is_context_detail_request(user_message):
        reply = build_context_detail_reply(request, user_message)
        if request.user.is_authenticated:
            ChatHistory.objects.create(user=request.user, message=user_message, reply=reply)
        return JsonResponse({"reply": reply})

    if intent_name == "add_to_cart" or is_add_to_cart_request(user_message):
        reply = build_add_to_cart_reply(request, select_product_for_cart(request, user_message))
        if request.user.is_authenticated:
            ChatHistory.objects.create(user=request.user, message=user_message, reply=reply)
        return JsonResponse({"reply": reply})

    products, filters = find_products_with_context(request, user_message, ai_intent=ai_intent)
    remember_products(request, products, message=user_message, filters=filters)
    fallback_reply = build_fallback_reply(products, filters)
    reply = get_ai_reply(request, user_message, products, filters, fallback_reply)

    if request.user.is_authenticated:
        ChatHistory.objects.create(user=request.user, message=user_message, reply=reply)

    return JsonResponse({"reply": reply})
