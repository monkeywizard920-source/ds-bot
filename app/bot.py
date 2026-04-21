from __future__ import annotations

from aiogram import Bot, Dispatcher
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.telegram import TelegramAPIServer

from app.config import Settings
from app.handlers.chat import router as chat_router
from app.services.context_service import ContextService
from app.services.llm_service import LLMService


def create_bot(settings: Settings, proxy_url: str | None = None) -> Bot:
    session_kwargs = {}
    if settings.telegram_api_base_url:
        session_kwargs["api"] = TelegramAPIServer.from_base(settings.telegram_api_base_url)

    session = AiohttpSession(
        proxy=proxy_url,
        timeout=settings.telegram_request_timeout,
        **session_kwargs,
    )
    return Bot(token=settings.bot_token, session=session)


def create_dispatcher(
    *,
    settings: Settings,
    context_service: ContextService,
    llm_service: LLMService,
) -> Dispatcher:
    dispatcher = Dispatcher(
        settings=settings,
        context_service=context_service,
        llm_service=llm_service,
    )
    dispatcher.include_router(chat_router)
    return dispatcher
