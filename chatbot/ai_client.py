import os

import requests
from django.conf import settings as django_settings
from dotenv import load_dotenv


load_dotenv()


PROVIDERS = {
    "openai": {
        "name": "OpenAI",
        "api_key_env": "OPENAI_API_KEY",
        "model_env": "OPENAI_MODEL",
        "base_url_env": "OPENAI_BASE_URL",
        "default_base_url": "https://api.openai.com/v1",
        "default_model": "gpt-4o-mini",
        "api_key_aliases": ("GPT_API_KEY",),
        "model_aliases": ("GPT_MODEL",),
    },
    "groq": {
        "name": "Groq",
        "api_key_env": "GROQ_API_KEY",
        "model_env": "GROQ_MODEL",
        "base_url_env": "GROQ_BASE_URL",
        "default_base_url": "https://api.groq.com/openai/v1",
        "default_model": "llama-3.1-8b-instant",
    },
}


def _selected_provider() -> str:
    provider = os.getenv("AI_PROVIDER", "").strip().lower()

    if provider == "openai" and _setting_value("OPENAI_API_KEY"):
        return provider

    if _setting_value("OPENAI_API_KEY"):
        return "openai"

    if provider == "groq" and _setting_value("GROQ_API_KEY"):
        return provider

    if _setting_value("GROQ_API_KEY"):
        return "groq"

    return "openai"


def _setting_value(name: str, default: str = "") -> str:
    value = os.getenv(name)
    if value:
        return value.strip()

    for config in PROVIDERS.values():
        if name == config["api_key_env"]:
            for alias in config.get("api_key_aliases", ()):
                value = os.getenv(alias)
                if value:
                    return value.strip()

        if name == config["model_env"]:
            for alias in config.get("model_aliases", ()):
                value = os.getenv(alias)
                if value:
                    return value.strip()

    try:
        value = getattr(django_settings, name, default)
    except Exception:
        value = default

    return str(value or "").strip()


def get_ai_settings() -> dict:
    provider = _selected_provider()
    config = PROVIDERS[provider]

    return {
        "provider": provider,
        "provider_name": config["name"],
        "api_key_env": config["api_key_env"],
        "api_key": _setting_value(config["api_key_env"]),
        "model": _setting_value(config["model_env"], config["default_model"]),
        "base_url": _setting_value(config["base_url_env"], config["default_base_url"]).rstrip("/"),
    }


def create_chat_completion(messages: list, temperature: float = 0.7, max_tokens: int = 1024) -> str:
    settings = get_ai_settings()

    if not settings["api_key"]:
        raise RuntimeError(
            f"Missing {settings['api_key_env']} for {settings['provider_name']}."
        )

    response = requests.post(
        f"{settings['base_url']}/chat/completions",
        headers={
            "Authorization": f"Bearer {settings['api_key']}",
            "Content-Type": "application/json",
        },
        json={
            "model": settings["model"],
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        },
        timeout=60,
    )

    try:
        data = response.json()
    except ValueError as exc:
        raise RuntimeError(
            f"{settings['provider_name']} returned a non-JSON response."
        ) from exc

    if response.status_code >= 400:
        error = data.get("error", {})
        message = error.get("message") if isinstance(error, dict) else str(error)
        raise RuntimeError(
            f"{settings['provider_name']} API error {response.status_code}: {message or response.text}"
        )

    try:
        return data["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError(
            f"{settings['provider_name']} returned an unexpected response format."
        ) from exc
