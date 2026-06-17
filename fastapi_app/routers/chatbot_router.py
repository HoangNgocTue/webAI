import os
import re

from fastapi import APIRouter, Request, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from ..database import get_db
from ..dependencies import BaseContext
from ..models import SupportTicket
from ..chatbot_service import get_system_prompt, get_history, save_history
from ..templates_config import templates

router = APIRouter(tags=["chatbot"])


@router.get("/chatbot/", name="chatbot_view")
async def chatbot_view(request: Request, ctx: BaseContext = Depends(BaseContext)):
    return templates.TemplateResponse(request, "chatbot.html", ctx.dict())


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
            return JSONResponse({"reply": reply})
        return JSONResponse({"reply": f"❌ Không tìm thấy ticket **{ticket_id}**. Bạn kiểm tra lại mã ticket nhé."})

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
            return JSONResponse({
                "reply": (
                    f"✅ Đã lưu email **{email}** cho ticket **{pending_ticket_id}**.\n"
                    f"Mình sẽ gửi thông báo ngay khi ticket được xử lý nhé! 😊"
                )
            })

    # --- Flow 3: Claude AI ---
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        return JSONResponse({"reply": "⚠️ Chưa cấu hình ANTHROPIC_API_KEY."}, status_code=500)

    try:
        from anthropic import Anthropic
        client = Anthropic(api_key=api_key)
        system_prompt = get_system_prompt(db)
        history = get_history(request)
        messages = history + [{"role": "user", "content": user_message}]

        response = client.messages.create(
            model=os.getenv("CLAUDE_MODEL", "claude-sonnet-4-6"),
            max_tokens=1024,
            system=system_prompt,
            messages=messages,
        )
        reply = response.content[0].text

        ticket_info = None
        if "[SUPPORT_TICKET:" in reply:
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

        save_history(request, user_message, reply)
        return JSONResponse({"reply": reply, "ticket": ticket_info})

    except Exception as e:
        print(f"Claude Error: {type(e).__name__} - {e}")
        return JSONResponse(
            {"reply": "⚠️ AI chatbot đang gặp lỗi. Vui lòng thử lại sau."},
            status_code=500,
        )
