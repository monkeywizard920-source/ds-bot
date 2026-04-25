from __future__ import annotations

import asyncio
import logging
import os
import aiohttp

from aiogram import Bot
from aiogram.exceptions import TelegramNetworkError, TelegramConflictError
from aiohttp import web

from app.bot import create_bot, create_dispatcher
from app.config import Settings
from app.logging_config import setup_logging
from app.repositories.message_repository import MessageRepository
from app.services.context_service import ContextService
from app.services.llm_service import LLMService
from app.services.proxy_service import ProxyService

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

async def keep_alive_ping(url: str | None):
    """Фоновая задача для самопрозвона, чтобы Render не усыплял бота."""
    if not url:
        logger.warning("RENDER_EXTERNAL_URL не задан. Self-ping отключен.")
        return

    logger.info("Self-ping запущен для URL: %s", url)
    async with aiohttp.ClientSession() as session:
        while True:
            await asyncio.sleep(60)  # Пинг каждую минуту
            try:
                async with session.get(url) as response:
                    logger.debug("Self-ping status: %s", response.status)
            except Exception as e:
                logger.error("Ошибка self-ping: %s", e)

async def main() -> None:
    setup_logging()
    settings = Settings()

    # Инициализируем прокси-сервис
    proxy_service = ProxyService(settings.proxy_file)
    await proxy_service.load_proxies()
    await proxy_service.find_working_proxy()

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
    asyncio.create_task(keep_alive_ping(settings.render_external_url))

    while True:
        logger.info("Starting Telegram polling (direct connection)")
        bot = create_bot(settings)
        try:
            # Очищаем старые сообщения при старте, чтобы не было конфликтов и спама
            await bot.delete_webhook(drop_pending_updates=True)
            await dispatcher.start_polling(bot, skip_updates=True)
        except TelegramConflictError:
            logger.error(
                "Обнаружен конфликт: запущен другой экземпляр бота. "
                "Если вы на Render, это нормально при деплое. Ждем 15 секунд..."
            )
            try:
                await bot.session.close()
            finally:
                await asyncio.sleep(15)
        except TelegramNetworkError as error:
            logger.warning(
                "Telegram API is unavailable: %s. Retrying in %s seconds.",
                error,
                settings.polling_retry_delay,
            )
            await bot.session.close()
            # Пробуем сменить прокси при ошибке сети
            await proxy_service.rotate_proxy()
            await asyncio.sleep(settings.polling_retry_delay)
        else:
            break

if __name__ == "__main__":
    asyncio.run(main())