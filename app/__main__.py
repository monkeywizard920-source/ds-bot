from __future__ import annotations

import asyncio
import logging
import os

from aiogram import Bot
from aiogram.exceptions import TelegramNetworkError, TelegramConflictError
from aiohttp import web

from app.bot import create_bot, create_dispatcher
from app.config import Settings
from app.logging_config import setup_logging
from app.repositories.message_repository import MessageRepository
from app.services.context_service import ContextService
from app.services.llm_service import LLMService

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

    dispatcher = create_dispatcher(
        settings=settings,
        context_service=context_service,
        llm_service=llm_service,
    )

    # Запускаем фоновый веб-сервер для Render
    asyncio.create_task(start_health_check_server())

    while True:
        logger.info("Starting Telegram polling (direct connection)")
        bot = create_bot(settings)
        try:
            await dispatcher.start_polling(bot)
        except TelegramConflictError:
            logger.error(
                "Обнаружен конфликт: запущен другой экземпляр бота. "
                "Если вы на Render, это нормально при деплое. Ждем 15 секунд..."
            )
            await bot.session.close()
            await asyncio.sleep(15)
        except TelegramNetworkError as error:
            logger.warning(
                "Telegram API is unavailable: %s. Retrying in %s seconds.",
                error,
                settings.polling_retry_delay,
            )
            await bot.session.close()
            await asyncio.sleep(settings.polling_retry_delay)
        else:
            break

if __name__ == "__main__":
    asyncio.run(main())