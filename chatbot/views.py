from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

import os
import json

from dotenv import load_dotenv

from app.models import Product
from chatbot.claude_client import get_claude_client
from chatbot.models import SupportTicket


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
Bạn là AI chatbot hỗ trợ khách hàng của Đà Nẵng Store.

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

PHÂN LOẠI YÊU CẦU HỖ TRỢ:
Khi khách hàng gặp sự cố hoặc báo lỗi, hãy xác định đây là yêu cầu hỗ trợ kỹ thuật và phân loại theo một trong các nhóm sau:
- order_payment: Lỗi đặt hàng, lỗi thanh toán, không nhận được xác nhận đơn hàng
- account: Không đăng nhập được, quên mật khẩu, không tạo được tài khoản
- cart_product: Không thêm được vào giỏ, ảnh không hiển thị, thông số sản phẩm sai
- delivery_warranty: Chưa nhận được hàng, yêu cầu đổi trả, yêu cầu bảo hành

KHI PHÁT HIỆN YÊU CẦU HỖ TRỢ:
Nếu khách đang gặp sự cố hoặc báo lỗi (không phải chỉ hỏi thông tin sản phẩm), hãy:
1. Trả lời thân thiện, thể hiện sự đồng cảm
2. Thêm dòng đặc biệt ở CUỐI phản hồi theo định dạng chính xác:
   [SUPPORT_TICKET:category]
   Trong đó category là một trong: order_payment, account, cart_product, delivery_warranty, other

Ví dụ nếu khách báo không đặt hàng được:
"Rất tiếc khi bạn gặp khó khăn! ... [SUPPORT_TICKET:order_payment]"

QUY TẮC CHUNG:
- Chỉ trả lời dựa trên dữ liệu được cung cấp
- Không tự bịa thông tin
- Trả lời thân thiện, ngắn gọn
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
        return JsonResponse({"reply": "Phương thức không hợp lệ"}, status=400)

    # =========================================================
    # READ MESSAGE
    # =========================================================
    try:
        data = json.loads(request.body)
        user_message = data.get("message", "").strip()
    except:
        user_message = (request.POST.get("message") or "").strip()

    if not user_message:
        return JsonResponse({"reply": "Vui lòng nhập tin nhắn."})

    import re

    # =========================================================
    # LUỒNG 1: Khách kiểm tra trạng thái ticket (TKT-XXXXXX)
    # =========================================================
    ticket_id_match = re.search(r'\bTKT-[A-F0-9]{6}\b', user_message.upper())
    if ticket_id_match:
        ticket_id = ticket_id_match.group(0)
        try:
            ticket = SupportTicket.objects.get(ticket_id=ticket_id)
            status_map = {
                'open':        '🔴 Chờ xử lý',
                'in_progress': '🟡 Đang xử lý',
                'resolved':    '🟢 Đã giải quyết',
            }
            reply = (
                f"📋 **Thông tin ticket {ticket.ticket_id}**\n"
                f"- Loại: {ticket.get_category_display()}\n"
                f"- Trạng thái: {status_map.get(ticket.status, ticket.status)}\n"
                f"- Ngày tạo: {ticket.created_at.strftime('%d/%m/%Y %H:%M')}\n"
            )
            if ticket.staff_note:
                reply += f"- Ghi chú nhân viên: {ticket.staff_note}"
            return JsonResponse({"reply": reply})
        except SupportTicket.DoesNotExist:
            return JsonResponse({"reply": f"❌ Không tìm thấy ticket **{ticket_id}**. Vui lòng kiểm tra lại mã."})

    # =========================================================
    # LUỒNG 2: Khách cung cấp email cho ticket đang chờ
    # =========================================================
    email_match = re.search(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b', user_message)
    pending_ticket_id = request.session.get('pending_email_ticket')
    if email_match and pending_ticket_id:
        email = email_match.group(0)
        try:
            ticket = SupportTicket.objects.get(ticket_id=pending_ticket_id)
            ticket.customer_email = email
            ticket.save()
            request.session.pop('pending_email_ticket', None)
            return JsonResponse({
                "reply": (
                    f"✅ Đã lưu email **{email}** cho ticket **{pending_ticket_id}**.\n"
                    f"Chúng tôi sẽ gửi thông báo khi ticket được xử lý."
                )
            })
        except SupportTicket.DoesNotExist:
            pass

    # =========================================================
    # LUỒNG 3: Gọi Claude AI
    # =========================================================
    client = get_claude_client()
    if not client:
        return JsonResponse({"reply": "⚠️ Chưa cấu hình ANTHROPIC_API_KEY."}, status=500)

    base_prompt = get_base_prompt()

    try:
        response = client.messages.create(
            model=os.getenv("CLAUDE_MODEL", "claude-sonnet-4-6"),
            max_tokens=1024,
            system=base_prompt,
            messages=[{"role": "user", "content": user_message}],
        )
        reply = response.content[0].text

        # Tạo support ticket nếu AI phát hiện sự cố
        ticket_info = None
        if "[SUPPORT_TICKET:" in reply:
            match = re.search(r'\[SUPPORT_TICKET:(\w+)\]', reply)
            if match:
                category = match.group(1)
                valid_categories = [c[0] for c in SupportTicket.CATEGORY_CHOICES]
                if category not in valid_categories:
                    category = 'other'
                ticket = SupportTicket.objects.create(
                    category=category,
                    description=user_message,
                )
                ticket_info = {
                    "ticket_id": ticket.ticket_id,
                    "category": ticket.get_category_display(),
                }
                # Lưu vào session để nhận email ở tin nhắn tiếp theo
                request.session['pending_email_ticket'] = ticket.ticket_id
                reply = re.sub(r'\s*\[SUPPORT_TICKET:\w+\]', '', reply).strip()
                reply += (
                    f"\n\n📋 Mã ticket của bạn: **{ticket.ticket_id}**\n"
                    f"Nếu muốn nhận thông báo qua email khi được xử lý, "
                    f"hãy nhập địa chỉ email của bạn ngay bây giờ."
                )

        return JsonResponse({"reply": reply, "ticket": ticket_info})

    except Exception as e:
        print(f"Claude Error: {type(e).__name__} - {e}")
        return JsonResponse(
            {"reply": "⚠️ AI chatbot đang gặp lỗi. Vui lòng thử lại sau."},
            status=500,
        )