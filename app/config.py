from __future__ import annotations

import logging
from pathlib import Path

from pydantic import Field, field_validator, AliasChoices, ValidationError
from typing import Annotated
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Оставляем только один четкий алиас, чтобы исключить путаницу
    discord_token: str = Field(alias="DISCORD_TOKEN")
    command_prefix: str = Field(default="!", alias="COMMAND_PREFIX")
    render_external_url: str | None = Field(default=None, alias="RENDER_EXTERNAL_URL")
    admin_ids: list[int] = Field(default=[1365594992193830912], alias="ADMIN_IDS")
    excluded_ids: list[int] = Field(default=[], alias="EXCLUDED_IDS")

    groq_api_key: str | None = Field(default=None, alias="GROQ_API_KEY")
    two_api_key: str | None = Field(default=None, alias="TWO_API_KEY")
    tree_api_key: str | None = Field(default=None, alias="TREE_API_KEY")
    four_api_key: str | None = Field(default=None, alias="FOUR_API_KEY")
    five_api_key: str | None = Field(default=None, alias="FIVE_API_KEY")
    groq_model: str = Field(default="llama-3.3-70b-versatile", alias="GROQ_MODEL")
    groq_base_url: str = Field(default="https://api.groq.com/openai/v1", alias="GROQ_BASE_URL")

    llm_temperature: float = Field(default=0.6, alias="LLM_TEMPERATURE", ge=0.0, le=2.0)
    llm_top_p: float = Field(default=0.95, alias="LLM_TOP_P", ge=0.0, le=1.0)
    llm_max_tokens: int = Field(default=1024, alias="LLM_MAX_TOKENS", ge=1)

    database_path: Path = Field(default=Path("storage/bot.sqlite3"), alias="DATABASE_PATH")
    discord_log_channel_id: int = Field(default=1497682736817635590, alias="DISCORD_LOG_CHANNEL_ID")
    message_log_path: Path = Field(default=Path("storage/messages.log"), alias="MESSAGE_LOG_PATH")
    max_context_messages: int = Field(default=40, alias="MAX_CONTEXT_MESSAGES", ge=1)
    max_context_chars: int = Field(default=12000, alias="MAX_CONTEXT_CHARS", ge=1)
    max_reply_chars: int = Field(default=4096, alias="MAX_REPLY_CHARS", ge=1)
    answer_on_every_message: bool = Field(default=False, alias="ANSWER_ON_EVERY_MESSAGE")
    
    @field_validator("admin_ids", mode="before")
    @classmethod
    def parse_admin_ids(cls, v):
        """Гибкий парсинг списка ID из строки (с запятыми, пробелами или скобками)."""
        if isinstance(v, str):
            import json
            cleaned = v.strip()
            if cleaned.startswith("[") and cleaned.endswith("]"):
                try:
                    return json.loads(cleaned)
                except:
                    cleaned = cleaned[1:-1]
            return [int(x.strip()) for x in cleaned.split(",") if x.strip()]
        return v

    @field_validator("max_context_messages", mode="before")
    def validate_max_context_messages(cls, v):
        if v == "" or v is None:
            return 40
        return v

    @field_validator("discord_token", mode="before")
    @classmethod
    def clean_discord_token(cls, v: str | None) -> str:
        """Очищает токен от кавычек и пробелов, предотвращая ошибку Improper token."""
        if not v:
            raise ValueError("DISCORD_TOKEN не может быть пустым")
        cleaned = str(v).strip().strip("\"'")
        if cleaned.count(".") < 2:
             # Discord токены обычно состоят из 3 частей, разделенных точками
             logger.warning("Предупреждение: DISCORD_TOKEN не похож на стандартный токен Discord.")
        return cleaned
