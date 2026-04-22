from __future__ import annotations

import asyncio
import os
import re

from app.config import Settings
from app.services.llm_service import LLMService, _clean_api_key


async def main() -> None:
    settings = Settings()
    service = LLMService(settings)
    raw_key = (settings.groq_api_key or "").strip().strip("\"'")
    cleaned_key = _clean_api_key(raw_key)
    placeholder_values = {"$NVIDIA_API_KEY", "NVIDIA_API_KEY", "nvapi-your-key", "sk-your-key"}

    print(f"configured={service.is_configured}")
    print(f"model={settings.groq_model}")
    print(f"key_length={len(raw_key)}")

    env_reference = _env_reference_name(raw_key)
    if env_reference and not os.getenv(env_reference):
        print("key_status=env_reference_missing")
        print(f"Переменная окружения {env_reference} не задана. Вставьте реальный ключ в .env.")
        return

    if raw_key in placeholder_values and not cleaned_key:
        print("key_status=placeholder")
        print("В .env все еще стоит пример ключа. Замените его на настоящий NVIDIA API key.")
        return

    if not cleaned_key:
        print("key_status=missing")
        print("В .env нет GROQ_API_KEY.")
        return

    print("key_status=set")

    answer = await service.answer(
        context="Контекст теста: пользователь проверяет доступ к LLM.",
        question="Ответь одним коротким словом: работает?",
        chat_title="test",
    )
    print(answer[:1000])


def _env_reference_name(value: str) -> str | None:
    match = re.fullmatch(r"\$([A-Za-z_][A-Za-z0-9_]*)", value)
    return match.group(1) if match else None


if __name__ == "__main__":
    asyncio.run(main())
