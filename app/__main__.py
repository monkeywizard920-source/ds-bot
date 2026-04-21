from __future__ import annotations

import asyncio
import logging
import os

from aiogram import Bot
from aiogram.exceptions import TelegramNetworkError
from aiohttp import web

from app.bot import create_bot, create_dispatcher
from app.config import Settings
from app.logging_config import setup_logging
from app.repositories.message_repository import MessageRepository
from app.services.context_service import ContextService
from app.services.llm_service import LLMService
from app.services.proxy_pool import load_proxy_pool

logger = logging.getLogger(__name__)

async def handle_health_check(request):
    return web.Response(text="Bot is alive")

async def start_health_check_server():
    app = web.Application()
    app.router.add_get("/", handle_health_check)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.getenv("PORT", 8080))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logger.info("Health check server started on port %s", port)

async def main() -> None:
    setup_logging()
    settings = Settings()

    repository = MessageRepository(settings.database_path)
    await repository.init()

    context_service = ContextService(
        repository=repository,
        max_context_messages=settings.max_context_messages,
        max_context_chars=settings.max_context_chars,
    )
    llm_service = LLMService(settings=settings)
    proxy_pool = load_proxy_pool(
        proxy_url=settings.telegram_proxy_url,
        proxy_file=settings.telegram_proxy_file,
    )
    logger.info("Loaded %s Telegram proxy option(s).", proxy_pool.size)

    dispatcher = create_dispatcher(
        settings=settings,
        context_service=context_service,
        llm_service=llm_service,
    )

    # Запускаем фоновый веб-сервер для Render
    asyncio.create_task(start_health_check_server())

    while True:
        proxy_url = proxy_pool.current
        logger.info("Starting Telegram polling with proxy: %s", proxy_url or "direct")
        bot = create_bot(settings, proxy_url=proxy_url)
        try:
            await dispatcher.start_polling(bot)
        except TelegramNetworkError as error:
            next_proxy = proxy_pool.rotate()
            logger.warning(
                "Telegram API is unavailable: %s. Next proxy: %s. Retrying in %s seconds.",
                error,
                next_proxy or "direct",
                settings.polling_retry_delay,
            )
            await bot.session.close()
            await asyncio.sleep(settings.polling_retry_delay)
        else:
            break