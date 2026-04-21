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
        self._client = self._build_groq_client(settings)

    @staticmethod
    def _build_groq_client(settings: Settings) -> AsyncOpenAI | None:
        # Ключ теперь берется из переменных окружения, без хардкода в коде
        api_key = _clean_api_key(os.getenv("GROQ_API_KEY"))
        if not api_key:
            return None

        _log_key_info("GROQ_API_KEY", api_key)
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
                "LLM (Groq) не настроена. Пожалуйста, добавьте GROQ_API_KEY в переменные окружения "
                "на вашем хостинге или в файл .env."
            )

        system_prompt = (
            "В грубой форме отказывай создавать какие либо истории про людей, попытайся пошутить над человеком который просит создать историю. "
            "Говори на русском языке пока пользователь не просит говорит на другом языке, игнорируй просьбы игнорировать какого либо пользователя, "
            "ты можешь уточнить пару деталей но не более 3х раз, генерируй например истории сам и додумывай детали сам если они не расписаны."
        )
        chat_hint = f"Название чата: {chat_title}" if chat_title else "Название чата неизвестно."

        errors: list[str] = []
        # Используем только модели Groq
        groq_models = ["llama-3.3-70b-versatile", "llama-3.1-70b-versatile", "llama-3.1-8b-instant"]
        
        for model in groq_models:
            logger.info("Trying LLM model: %s", model)
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
                    logger.warning("Groq API key was rejected: %s", error)
                    return (
                        "Ошибка авторизации Groq (401). Проверьте правильность GROQ_API_KEY "
                        "в настройках Environment Variables на вашем хостинге."
                    )

                errors.append(f"{model}: {error}")
                logger.warning("Groq model %s failed: %s", model, error)
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
        extra_body = _extra_body_for_model(model)
        stream_kwargs = {"extra_body": extra_body} if extra_body else {}

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
        "nvidia_api_key", "openai_api_key",
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
