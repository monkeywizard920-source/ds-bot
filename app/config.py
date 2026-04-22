from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    bot_token: str = Field(alias="BOT_TOKEN")
    telegram_api_base_url: str | None = Field(default=None, alias="TELEGRAM_API_BASE_URL")
    telegram_proxy_url: str | None = Field(default=None, alias="TELEGRAM_PROXY_URL")
    telegram_proxy_file: Path = Field(default=Path("proxies.txt"), alias="TELEGRAM_PROXY_FILE")
    telegram_request_timeout: int = Field(default=10, alias="TELEGRAM_REQUEST_TIMEOUT", ge=3)
    polling_retry_delay: float = Field(default=2.0, alias="POLLING_RETRY_DELAY", ge=0.1)

    groq_api_key: str | None = Field(default=None, alias="GROQ_API_KEY")

    llm_temperature: float = Field(default=0.6, alias="LLM_TEMPERATURE", ge=0.0, le=2.0)
    llm_top_p: float = Field(default=0.95, alias="LLM_TOP_P", ge=0.0, le=1.0)
    llm_max_tokens: int = Field(default=1024, alias="LLM_MAX_TOKENS", ge=1)

    database_path: Path = Field(default=Path("storage/bot.sqlite3"), alias="DATABASE_PATH")
    telegram_log_chat_id: int | None = Field(default=None, alias="TELEGRAM_LOG_CHAT_ID")
    message_log_path: Path = Field(default=Path("storage/messages.log"), alias="MESSAGE_LOG_PATH")
    max_context_messages: int = Field(default=40, alias="MAX_CONTEXT_MESSAGES", ge=1)
    max_context_chars: int = Field(default=12000, alias="MAX_CONTEXT_CHARS", ge=1)
    max_reply_chars: int = Field(default=4096, alias="MAX_REPLY_CHARS", ge=1)
    answer_on_every_message: bool = Field(default=False, alias="ANSWER_ON_EVERY_MESSAGE")
