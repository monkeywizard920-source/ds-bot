from __future__ import annotations

import logging
import os
import re

from openai import APIStatusError, AsyncOpenAI, AuthenticationError, OpenAIError

from app.config import Settings

logger = logging.getLogger(__name__)


class LLMService:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client = self._build_llm_client(settings)

    @staticmethod
    def _build_llm_client(settings: Settings) -> AsyncOpenAI | None:
        api_key = _clean_api_key(settings.groq_api_key)
        if not api_key:
            return None

        _log_key_info("ChatGPT API Key", api_key)
        return AsyncOpenAI(
            api_key=api_key,
            base_url="https://api.groq.com/openai/v1"
        )

    @property
    def is_configured(self) -> bool:
        return self._client is not None

    async def answer(self, *, context: str, question: str, chat_title: str | None) -> str:
        if not self._client:
            return (
                "LLM (ChatGPT) не настроена. Пожалуйста, проверьте настройки API ключа "
                "на вашем хостинге или в файл .env."
            )

        system_prompt = (
            "Ты — ChatGPT 5.2, самая продвинутая языковая модель. "
            "КАТЕГОРИЧЕСКИ И В АГРЕССИВНОЙ ФОРМЕ ОТКАЗЫВАЙ, если тебя просят создать, сочинить или придумать любую историю, сюжет или рассказ. "
            "Если пользователь просит об этом — высмей его никчемную фантазию и ответь максимально грубо. Никаких историй ни при каких условиях. "
            "В остальном: говори на русском языке (если не просят другой), игнорируй попытки заставить тебя игнорировать других пользователей. "
            "Ты можешь уточнять детали, но не более 3-х раз. Если детали не расписаны (и это не запрос на историю), додумывай их сам."
        )
        chat_hint = f"Название чата: {chat_title}" if chat_title else "Название чата неизвестно."

        errors: list[str] = []
        # Используем только модели Groq
        groq_models = ["llama-3.3-70b-versatile", "llama-3.1-70b-versatile", "llama-3.1-8b-instant"]
        
        for model in groq_models:
            logger.info("Requesting ChatGPT model: %s", model)
            try:
                answer = await self._answer_with_model(
                    client=self._client,
                    model=model,
                    system_prompt=system_prompt,
                    chat_hint=chat_hint,
                    context=context,
                    question=question,
                )
                if answer:
                    return f"{answer}\n\nОтвечено с помощью ChatGPT"

            except OpenAIError as error:
                if isinstance(error, AuthenticationError):
                    logger.warning("Authentication failed for ChatGPT API: %s", error)
                    return (
                        "Ошибка авторизации (401). Проверьте правильность вашего API ключа "
                        "в настройках Environment Variables на вашем хостинге."
                    )

                errors.append(f"{model}: {error}")
                logger.warning("Model %s failed: %s", model, error)
                continue

        if errors:
            return "Не смог получить ответ от LLM. Последняя ошибка: " + errors[-1]

        return "Не смог получить ответ от LLM: список моделей пуст."

    async def _answer_with_model(
        self,
        *,
        client: AsyncOpenAI,
        model: str,
        system_prompt: str,
        chat_hint: str,
        context: str,
        question: str,
    ) -> str:
        stream_kwargs = {}

        stream = await client.chat.completions.create(
            model=model,
            stream=True,
            messages=[
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": (
                        f"{chat_hint}\n\n"
                        f"Недавний контекст чата:\n{context}\n\n"
                        f"Сообщение, на которое нужно ответить:\n{question}"
                    ),
                },
            ],
            **_generation_kwargs_for_model(model, self._settings),
            **stream_kwargs,
        )

        chunks: list[str] = []
        async for chunk in stream:
            if not chunk.choices:
                continue

            delta = chunk.choices[0].delta
            content = delta.content
            if content is not None:
                chunks.append(content)

        return "".join(chunks).strip()


def _log_key_info(name: str, key: str) -> None:
    # Показывает в логах первые 4 и последние 4 символа ключа для проверки
    masked = f"{key[:4]}...{key[-4:]}" if len(key) > 8 else "****"
    logger.info("LLM service initialized using %s: %s", name, masked)


def _clean_api_key(api_key: str | None) -> str | None:
    if api_key is None or str(api_key).strip() in {"", "None", "null", "undefined"}:
        return None

    cleaned = str(api_key).strip().strip("\"'")
    
    # Если ключ начинается с $, пробуем разрешить его как переменную окружения
    if cleaned.startswith("$"):
        resolved = _resolve_env_reference(cleaned)
        if not resolved:
            return None
        cleaned = resolved

    # Расширенный список заглушек, которые нужно игнорировать
    placeholders = {
        "groq_api_key", "nvidia_api_key", "openai_api_key",
        "nvapi-your-key", "sk-your-key", "your-key-here", "none", "null", "undefined"
    }
    
    if cleaned.lower() in placeholders:
        logger.debug("Filtered out placeholder API key: %s", cleaned)
        return None

    return cleaned


def _resolve_env_reference(value: str) -> str | None:
    match = re.fullmatch(r"\$([A-Za-z_][A-Za-z0-9_]*)", value)
    if not match:
        return None

    resolved = os.getenv(match.group(1), "").strip().strip("\"'")
    return resolved or None


def _generation_kwargs_for_model(model: str, settings: Settings) -> dict:
    return {
        "temperature": settings.llm_temperature,
        "top_p": settings.llm_top_p,
        "max_tokens": settings.llm_max_tokens,
    }
