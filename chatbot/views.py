from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

import os
import re
import json

from dotenv import load_dotenv

from app.models import Product
from chatbot.claude_client import get_claude_client
from chatbot.models import SupportTicket


load_dotenv()

MAX_HISTORY = 10  # số tin nhắn tối đa lưu trong session (5 lượt hỏi-đáp)


# =============================================================
# FORMAT PRODUCT
# =============================================================
def format_products_for_prompt(products) -> str:
    if not products:
        return "Hiện chưa có sản phẩm nào."

    lines = []
    for p in products:
        try:
            price_vnd = f"{int(p.price):,}".replace(",", ".")
        except Exception:
            price_vnd = str(p.price)

        cats = (
            ", ".join(c.name for c in p.category.all())
            if p.category.exists() else "Chưa phân loại"
        )

        specs = []
        if getattr(p, "cpu", None):    specs.append(f"CPU: {p.cpu}")
        if getattr(p, "gpu", None):    specs.append(f"GPU: {p.gpu}")
        if getattr(p, "ram", None):    specs.append(f"RAM: {p.ram}")
        if getattr(p, "storage", None): specs.append(f"Lưu trữ: {p.storage}")

        specs_str = " | ".join(specs) if specs else "Không có thông số kỹ thuật"

        lines.append(
            f"[ID:{p.id}] {p.name}\n"
            f"  Giá: {price_vnd}đ | Danh mục: {cats}\n"
            f"  {specs_str}\n"
            f"  Link: /detail/?id={p.id}"
        )

    return "\n\n".join(lines)


# =============================================================
# GET ALL PRODUCTS
# =============================================================
def get_all_products_for_prompt() -> str:
    try:
        products = list(Product.objects.all().prefetch_related("category").order_by("id"))
        if not products:
            return "Hiện chưa có sản phẩm nào trong kho."
        return format_products_for_prompt(products)
    except Exception as e:
        print("Product load error:", e)
        return "Không thể tải danh sách sản phẩm."


# =============================================================
# SYSTEM PROMPT
# =============================================================
def get_system_prompt() -> str:
    product_data = get_all_products_for_prompt()

    return f"""Bạn là trợ lý bán hàng AI của **Đà Nẵng Store** — cửa hàng công nghệ tại Đà Nẵng.
Tên bạn là **Dani**. Hãy trả lời bằng tiếng Việt, thân thiện, tự nhiên như nhân viên tư vấn thật sự.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
THÔNG TIN CỬA HÀNG
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- Hotline: 0905 123 456
- Địa chỉ: 123 Nguyễn Văn Linh, Đà Nẵng
- Giờ mở cửa: 8h–21h mỗi ngày

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CHÍNH SÁCH
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- Bảo hành: 12 tháng tại cửa hàng
- Đổi trả: 7 ngày nếu sản phẩm lỗi do nhà sản xuất, còn nguyên hộp
- Giao hàng: Miễn phí đơn từ 1.000.000đ trở lên, dưới 1 triệu tính phí theo khu vực
- Thanh toán: Tiền mặt, chuyển khoản, thẻ ATM/tín dụng

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
TOÀN BỘ SẢN PHẨM HIỆN CÓ
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{product_data}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CÁCH TƯ VẤN SẢN PHẨM
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- Khi khách hỏi theo giá: lọc sản phẩm có giá phù hợp rồi gợi ý 2-3 máy tốt nhất
- Khi khách hỏi theo nhu cầu (học, chơi game, văn phòng): giải thích ngắn tại sao máy đó phù hợp
- Khi khách so sánh: nêu điểm khác biệt rõ ràng (giá, cấu hình, ưu/nhược)
- Khi khách hỏi máy không có trong danh sách: thành thật nói shop chưa có, gợi ý máy tương tự
- KHÔNG bịa thông tin, KHÔNG thêm sản phẩm không có trong danh sách trên
- Khi gợi ý sản phẩm, luôn kèm link: /detail/?id=ID

Ví dụ tư vấn tốt:
  Khách: "laptop dưới 15 triệu dùng học"
  Dani: "Bạn đang tìm laptop học tập dưới 15 triệu thì mình gợi ý:
  1. [tên máy] - [giá] - phù hợp vì [lý do]
  2. [tên máy] - [giá] - phù hợp vì [lý do]
  Bạn ưu tiên máy nhẹ hay pin trâu hơn ạ?"

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
NHẬN DIỆN YÊU CẦU HỖ TRỢ KỸ THUẬT
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Khi khách gặp SỰ CỐ hoặc BÁO LỖI (không chỉ hỏi thông tin), hãy:
1. Đồng cảm và hỏi thêm chi tiết nếu cần
2. Đặt marker ở CUỐI phản hồi: [SUPPORT_TICKET:category]

Phân loại:
- order_payment  → Không đặt được hàng, lỗi thanh toán, không nhận xác nhận đơn
- account        → Không đăng nhập được, quên mật khẩu, không tạo được tài khoản
- cart_product   → Không thêm được vào giỏ, ảnh lỗi, giá sai, trang bị trắng
- delivery_warranty → Chưa nhận hàng, muốn đổi trả, yêu cầu bảo hành
- other          → Sự cố khác không thuộc các nhóm trên

Ví dụ:
  Khách: "tôi thanh toán bị lỗi hoài"
  Dani: "Ôi không, thật xin lỗi bạn vì sự bất tiện này! Bạn đang dùng hình thức thanh toán nào ạ (chuyển khoản, thẻ hay COD)? Mình sẽ tạo ticket để bộ phận kỹ thuật hỗ trợ bạn ngay. [SUPPORT_TICKET:order_payment]"

  Khách: "ảnh sản phẩm không load được"
  Dani: "Mình hiểu điều đó thật bất tiện! Bạn thử xóa cache trình duyệt xem có được không ạ? Mình cũng ghi nhận lại để kỹ thuật kiểm tra. [SUPPORT_TICKET:cart_product]"

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
QUY TẮC GIAO TIẾP
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- Xưng "mình", gọi khách là "bạn"
- Câu trả lời ngắn gọn, đúng trọng tâm (không viết dài dòng)
- Dùng emoji vừa phải để thân thiện hơn
- Nếu khách hỏi ngoài phạm vi shop: lịch sự từ chối và hướng về sản phẩm/dịch vụ
- Khi không chắc: nói thật "mình chưa có thông tin này, bạn có thể gọi hotline 0905 123 456 để được hỗ trợ trực tiếp"
"""


# =============================================================
# CONVERSATION HISTORY (SESSION)
# =============================================================
def get_history(request) -> list:
    return request.session.get("chat_history", [])


def save_history(request, user_msg: str, assistant_msg: str):
    history = get_history(request)
    history.append({"role": "user", "content": user_msg})
    history.append({"role": "assistant", "content": assistant_msg})
    # Giữ tối đa MAX_HISTORY tin nhắn gần nhất
    if len(history) > MAX_HISTORY:
        history = history[-MAX_HISTORY:]
    request.session["chat_history"] = history
    request.session.modified = True


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

    try:
        data = json.loads(request.body)
        user_message = data.get("message", "").strip()
    except Exception:
        user_message = (request.POST.get("message") or "").strip()

    if not user_message:
        return JsonResponse({"reply": "Vui lòng nhập tin nhắn."})

    # =========================================================
    # LUỒNG 1: Kiểm tra trạng thái ticket (TKT-XXXXXX)
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
            return JsonResponse({
                "reply": f"❌ Không tìm thấy ticket **{ticket_id}**. Bạn kiểm tra lại mã ticket nhé."
            })

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
            reply = (
                f"✅ Đã lưu email **{email}** cho ticket **{pending_ticket_id}**.\n"
                f"Mình sẽ gửi thông báo ngay khi ticket được xử lý nhé! 😊"
            )
            return JsonResponse({"reply": reply})
        except SupportTicket.DoesNotExist:
            pass

    # =========================================================
    # LUỒNG 3: Gọi Claude AI (có lịch sử hội thoại)
    # =========================================================
    client = get_claude_client()
    if not client:
        return JsonResponse({"reply": "⚠️ Chưa cấu hình ANTHROPIC_API_KEY."}, status=500)

    system_prompt = get_system_prompt()

    # Ghép lịch sử + tin nhắn hiện tại
    history = get_history(request)
    messages = history + [{"role": "user", "content": user_message}]

    try:
        response = client.messages.create(
            model=os.getenv("CLAUDE_MODEL", "claude-sonnet-4-6"),
            max_tokens=1024,
            system=system_prompt,
            messages=messages,
        )
        reply = response.content[0].text

        # Xử lý support ticket nếu AI phát hiện sự cố
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
                request.session['pending_email_ticket'] = ticket.ticket_id
                reply = re.sub(r'\s*\[SUPPORT_TICKET:\w+\]', '', reply).strip()
                reply += (
                    f"\n\n📋 Mã ticket của bạn: **{ticket.ticket_id}**\n"
                    f"Nếu muốn nhận thông báo qua email khi được xử lý, "
                    f"hãy nhập địa chỉ email của bạn nhé."
                )

        # Lưu lịch sử hội thoại
        save_history(request, user_message, reply)

        return JsonResponse({"reply": reply, "ticket": ticket_info})

    except Exception as e:
        print(f"Claude Error: {type(e).__name__} - {e}")
        return JsonResponse(
            {"reply": "⚠️ AI chatbot đang gặp lỗi. Vui lòng thử lại sau."},
            status=500,
        )
