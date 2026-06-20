import os
import re

from fastapi import APIRouter, Request, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from ..database import get_db
from ..dependencies import BaseContext
from ..models import SupportTicket
from ..chatbot_service import get_system_prompt, get_history, save_history
from ..chatbot_features import (
    build_add_to_cart_reply,
    build_auth_reply,
    build_context_detail_reply,
    build_fallback_reply,
    build_more_products_reply,
    build_remove_from_cart_reply,
    build_similar_products_reply,
    clear_cart_confirmation,
    clear_history,
    find_products_with_context,
    format_cart_reply,
    get_product_previews,
    get_chat_history_payload,
    get_special_reply,
    handle_pending_cart_confirmation,
    is_add_to_cart_request,
    is_auth_request,
    is_cart_view_request,
    is_context_detail_request,
    is_more_products_request,
    is_remove_from_cart_request,
    is_similar_products_request,
    record_chat_history,
    remember_products,
    sanitize_bot_reply,
)
from ..templates_config import templates

router = APIRouter(tags=["chatbot"])


def _selected_provider() -> str:
    provider = os.getenv("AI_PROVIDER", "anthropic").strip().lower()
    if provider in {"claude", "anthropic"}:
        return "anthropic"
    if provider in {"chatgpt", "gpt", "openai"}:
        return "openai"
    if provider == "groq":
        return "groq"
    return "anthropic"


def _selected_api_key(provider: str) -> str | None:
    return {
        "groq": os.getenv("GROQ_API_KEY"),
        "openai": os.getenv("OPENAI_API_KEY") or os.getenv("GPT_API_KEY"),
        "anthropic": os.getenv("ANTHROPIC_API_KEY"),
    }.get(provider)


def _provider_config_error(provider: str) -> str:
    if provider == "groq":
        return "⚠️ Chưa cấu hình GROQ_API_KEY."
    if provider == "openai":
        return "⚠️ Chưa cấu hình OPENAI_API_KEY hoặc GPT_API_KEY."
    return "⚠️ Chưa cấu hình ANTHROPIC_API_KEY."


def _create_ai_reply(provider: str, system_prompt: str, history: list, user_message: str) -> str:
    messages = history + [{"role": "user", "content": user_message}]

    if provider == "groq":
        from groq import Groq

        client = Groq(api_key=os.getenv("GROQ_API_KEY"))
        response = client.chat.completions.create(
            model=os.getenv("GROQ_MODEL", "llama-3.1-8b-instant"),
            messages=[{"role": "system", "content": system_prompt}] + messages,
            temperature=0.3,
            max_tokens=1024,
        )
        return response.choices[0].message.content or ""

    if provider == "openai":
        from openai import OpenAI

        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY") or os.getenv("GPT_API_KEY"))
        response = client.chat.completions.create(
            model=os.getenv("OPENAI_MODEL") or os.getenv("GPT_MODEL", "gpt-4o-mini"),
            messages=[{"role": "system", "content": system_prompt}] + messages,
            temperature=0.3,
            max_tokens=1024,
        )
        return response.choices[0].message.content or ""

    from anthropic import Anthropic

    client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    response = client.messages.create(
        model=os.getenv("CLAUDE_MODEL", "claude-sonnet-4-6"),
        max_tokens=1024,
        system=system_prompt,
        messages=messages,
    )
    return response.content[0].text


@router.get("/chatbot/", name="chatbot_view")
async def chatbot_view(request: Request, ctx: BaseContext = Depends(BaseContext)):
    return templates.TemplateResponse(request, "chatbot.html", ctx.dict())


@router.get("/api/chatbot/products/", name="chatbot_product_previews")
async def chatbot_product_previews(ids: str = "", db: Session = Depends(get_db)):
    return JSONResponse({"products": get_product_previews(db, ids)})


@router.post("/api/chatbot/clear/", name="chatbot_clear_history")
async def chatbot_clear_history(request: Request):
    clear_history(request)
    return JSONResponse({"ok": True})


@router.get("/api/chatbot/history/", name="chatbot_history")
async def chatbot_history(request: Request, db: Session = Depends(get_db)):
    return JSONResponse({"messages": get_chat_history_payload(db, request)})


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
            return JSONResponse({"reply": sanitize_bot_reply(reply)})
        return JSONResponse({"reply": sanitize_bot_reply(f"❌ Không tìm thấy ticket **{ticket_id}**. Bạn kiểm tra lại mã ticket nhé.")})

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
                "reply": sanitize_bot_reply(
                    f"✅ Đã lưu email **{email}** cho ticket **{pending_ticket_id}**.\n"
                    f"Mình sẽ gửi thông báo ngay khi ticket được xử lý nhé! 😊"
                )
            })

    provider = _selected_provider()

    # --- Flow 3: Product and cart features ported from the previous chatbot ---
    shopping_reply = handle_pending_cart_confirmation(db, request, user_message)
    if shopping_reply:
        shopping_reply = sanitize_bot_reply(shopping_reply)
        record_chat_history(db, request, user_message, shopping_reply)
        return JSONResponse({"reply": shopping_reply})

    special_reply = get_special_reply(user_message)
    if special_reply:
        special_reply = sanitize_bot_reply(special_reply)
        record_chat_history(db, request, user_message, special_reply)
        return JSONResponse({"reply": special_reply})

    if is_auth_request(user_message):
        clear_cart_confirmation(request)
        reply = sanitize_bot_reply(build_auth_reply())
        record_chat_history(db, request, user_message, reply)
        return JSONResponse({"reply": reply})

    if is_cart_view_request(user_message):
        clear_cart_confirmation(request)
        reply = sanitize_bot_reply(format_cart_reply(db, request))
        record_chat_history(db, request, user_message, reply)
        return JSONResponse({"reply": reply})

    if is_remove_from_cart_request(user_message):
        reply = sanitize_bot_reply(build_remove_from_cart_reply(db, request, user_message))
        record_chat_history(db, request, user_message, reply)
        return JSONResponse({"reply": reply})

    if is_more_products_request(user_message):
        clear_cart_confirmation(request)
        reply = sanitize_bot_reply(build_more_products_reply(db, request, user_message))
        record_chat_history(db, request, user_message, reply)
        return JSONResponse({"reply": reply})

    if is_similar_products_request(user_message):
        clear_cart_confirmation(request)
        reply = sanitize_bot_reply(build_similar_products_reply(db, request))
        record_chat_history(db, request, user_message, reply)
        return JSONResponse({"reply": reply})

    if is_context_detail_request(user_message):
        clear_cart_confirmation(request)
        reply = sanitize_bot_reply(build_context_detail_reply(db, request, user_message))
        record_chat_history(db, request, user_message, reply)
        return JSONResponse({"reply": reply})

    if is_add_to_cart_request(user_message):
        clear_cart_confirmation(request)
        reply = sanitize_bot_reply(build_add_to_cart_reply(db, request, user_message))
        record_chat_history(db, request, user_message, reply)
        return JSONResponse({"reply": reply})

    products, filters = find_products_with_context(db, request, user_message)
    if products or filters:
        clear_cart_confirmation(request)
        remember_products(request, products, message=user_message, filters=filters)
        reply = sanitize_bot_reply(build_fallback_reply(products, filters), products)
        record_chat_history(db, request, user_message, reply)
        return JSONResponse({"reply": reply})

    # --- Flow 4: General AI and support-ticket detection ---
    api_key = _selected_api_key(provider)
    if not api_key:
        return JSONResponse({"reply": _provider_config_error(provider)}, status_code=500)

    try:
        system_prompt = get_system_prompt(db)
        history = get_history(request)
        reply = _create_ai_reply(provider, system_prompt, history, user_message)

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

        reply = sanitize_bot_reply(reply)
        save_history(request, user_message, reply)
        return JSONResponse({"reply": reply, "ticket": ticket_info})

    except Exception as e:
        print(f"{provider.title()} Error: {type(e).__name__} - {e}")
        return JSONResponse(
            {"reply": "⚠️ AI chatbot đang gặp lỗi. Vui lòng thử lại sau."},
            status_code=500,
        )
