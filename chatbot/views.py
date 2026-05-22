from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

import os
import json

from dotenv import load_dotenv

from app.models import Product
from chatbot.groq_client import get_groq_client


# =============================================================
# LOAD ENV
# =============================================================
load_dotenv()


# =============================================================
# FORMAT PRODUCT RESPONSE
# =============================================================
def format_products_for_response(products: list) -> str:

    if not products:
        return "Không tìm thấy sản phẩm phù hợp."

    formatted = ""

    for i, product in enumerate(products, 1):

        try:
            price_vnd = f"{int(product.price):,}".replace(",", ".")
        except:
            price_vnd = str(product.price)

        categories = (
            ", ".join([cat.name for cat in product.category.all()])
            if product.category.exists()
            else "Chưa phân loại"
        )

        specs = []

        if getattr(product, "cpu", None):
            specs.append(f"CPU: {product.cpu}")

        if getattr(product, "gpu", None):
            specs.append(f"GPU: {product.gpu}")

        if getattr(product, "ram", None):
            specs.append(f"RAM: {product.ram}")

        if getattr(product, "storage", None):
            specs.append(f"Storage: {product.storage}")

        specs_str = " | ".join(specs) if specs else "Không có thông số"

        formatted += f"""
{i}. {product.name}
- Giá: {price_vnd}đ
- Danh mục: {categories}
- Thông số: {specs_str}
- Link: /detail/?id={product.id}

"""

    return formatted


# =============================================================
# GET PRODUCT DATA
# =============================================================
def get_product_data_for_prompt(limit: int = 5) -> str:

    try:

        products = Product.objects.all().order_by("id")[:limit]

        if not products.exists():
            return "Chưa có sản phẩm."

        return format_products_for_response(list(products))

    except Exception as e:

        print("Get Product Error:", e)

        return "Không thể tải dữ liệu sản phẩm."


# =============================================================
# SYSTEM PROMPT
# =============================================================
def get_base_prompt():

    product_data = get_product_data_for_prompt()

    return f"""
Bạn là AI chatbot bán hàng của Đà Nẵng Store.

THÔNG TIN CỬA HÀNG:
- Tên shop: Đà Nẵng Store
- Hotline: 0905 123 456
- Địa chỉ: 123 Nguyễn Văn Linh, Đà Nẵng

CHÍNH SÁCH:
- Bảo hành 12 tháng
- Đổi trả 7 ngày
- Miễn phí ship đơn trên 1 triệu

DANH SÁCH SẢN PHẨM:
{product_data}

QUY TẮC:
- Chỉ trả lời dựa trên dữ liệu được cung cấp
- Không tự bịa thông tin
- Trả lời thân thiện
- Nếu không biết thì nói chưa có thông tin
"""


# =============================================================
# CHATBOT PAGE
# =============================================================
def chatbot_view(request):

    return render(request, "chatbot/chatbot.html")


# =============================================================
# CHATBOT API
# =============================================================
@csrf_exempt
def chatbot_api(request):

    if request.method != "POST":

        return JsonResponse(
            {
                "reply": "Phương thức không hợp lệ"
            },
            status=400
        )

    # =========================================================
    # READ MESSAGE
    # =========================================================
    try:

        data = json.loads(request.body)

        user_message = data.get("message", "").strip()

    except:

        user_message = (request.POST.get("message") or "").strip()

    if not user_message:

        return JsonResponse(
            {
                "reply": "Vui lòng nhập tin nhắn."
            }
        )

    # =========================================================
    # GROQ CLIENT
    # =========================================================
    client = get_groq_client()

    if not client:

        return JsonResponse(
            {
                "reply": "⚠️ Chưa cấu hình GROQ_API_KEY."
            },
            status=500,
        )

    # =========================================================
    # PROMPT
    # =========================================================
    base_prompt = get_base_prompt()

    # =========================================================
    # GENERATE RESPONSE
    # =========================================================
    try:

        completion = client.chat.completions.create(
            model=os.getenv(
                "GROQ_MODEL",
                "llama-3.1-8b-instant"
            ),
            messages=[
                {
                    "role": "system",
                    "content": base_prompt
                },
                {
                    "role": "user",
                    "content": user_message
                }
            ],
            temperature=0.7,
            max_tokens=1024,
        )

        reply = completion.choices[0].message.content

        return JsonResponse(
            {
                "reply": reply
            }
        )

    # =========================================================
    # ERROR HANDLE
    # =========================================================
    except Exception as e:

        print(f"Groq Error: {type(e).__name__} - {e}")

        return JsonResponse(
            {
                "reply": "⚠️ AI chatbot đang gặp lỗi. Vui lòng thử lại sau."
            },
            status=500,
        )