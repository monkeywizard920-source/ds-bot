from __future__ import annotations

import logging
from aiogram import Bot, Dispatcher
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.telegram import TelegramAPIServer

from app.config import Settings
from app.handlers.chat import router as chat_router
from app.handlers.admin import router as admin_router
from app.services.context_service import ContextService
from app.services.llm_service import LLMService
from app.services.chat_control_service import ChatControlService
from app.services.proxy_service import ProxyService

logger = logging.getLogger(__name__)


def create_bot(settings: Settings) -> Bot:
    session_kwargs = {}
    if settings.telegram_api_base_url:
        session_kwargs["api"] = TelegramAPIServer.from_base(settings.telegram_api_base_url)

    # Настраиваем прокси
    proxy_service = ProxyService(settings.proxy_file)
    proxy = proxy_service.get_current_proxy()
    if proxy:
        session_kwargs["proxy"] = proxy
        logger.info(f"Using proxy: {proxy}")
    else:
        logger.warning("No working proxy found, connecting directly")

    session = AiohttpSession(
        timeout=settings.telegram_request_timeout,
        **session_kwargs,
    )
    bot = Bot(token=settings.bot_token, session=session)
    logger.info(f"Bot created with token: {settings.bot_token[:5]}...")
    return bot


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
        chat_control=ChatControlService(context_service._repository)
    )
    dispatcher.include_router(admin_router)
    dispatcher.include_router(chat_router)
    return dispatcher
