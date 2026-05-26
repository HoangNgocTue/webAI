from chatbot.ai_client import get_ai_settings


def get_groq_client():
    settings = get_ai_settings()

    if settings["provider"] != "groq" or not settings["api_key"]:
        return None

    raise RuntimeError(
        "get_groq_client() is deprecated. Use chatbot.ai_client.create_chat_completion() instead."
    )
