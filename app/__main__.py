from __future__ import annotations

import asyncio
import logging
import os
import aiohttp
import discord
from discord.ext import commands

from aiohttp import web

from app.config import Settings
from app.logging_config import setup_logging
from app.repositories.message_repository import MessageRepository
from app.services.context_service import ContextService
from app.services.llm_service import LLMService
from app.services.chat_control_service import ChatControlService
# Импортируем настройку Discord
from app.discord_handlers import setup_discord_handlers

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

    repository = MessageRepository(settings.database_path)
    await repository.init()

    context_service = ContextService(
        repository=repository,
        max_context_messages=settings.max_context_messages,
        max_context_chars=settings.max_context_chars,
    )
    llm_service = LLMService(settings=settings)
    chat_control = ChatControlService(repository)

    # Настройка Discord интентов
    intents = discord.Intents.default()
    intents.message_content = True
    intents.members = True

    # Отладочный вывод для проверки конфигурации
    token = settings.discord_token
    masked_token = f"{token[:10]}...{token[-10:]}" if len(token) > 20 else "INVALID"
    logger.info("Configuration Check:")
    logger.info(f" - DISCORD_TOKEN: {masked_token}")
    logger.info(f" - ADMIN_IDS: {settings.admin_ids}")
    logger.info(f" - COMMAND_PREFIX: {settings.command_prefix}")

    # Запускаем фоновый веб-сервер для Render
    asyncio.create_task(start_health_check_server())
    asyncio.create_task(keep_alive_ping(settings.render_external_url))

    logger.info("Starting Discord bot...")
    retry_delay = settings.discord_retry_delay
    while True:
        bot = commands.Bot(command_prefix=settings.command_prefix, intents=intents)
        bot.settings = settings
        bot.context_service = context_service
        bot.llm_service = llm_service
        bot.chat_control = chat_control
        setup_discord_handlers(bot)

        if settings.discord_log_channel_id:
            from app.discord_handlers import DiscordLogHandler
            # Настраиваем логирование ТОЛЬКО для специального логгера запросов
            request_logger = logging.getLogger("discord_request_log")
            request_logger.setLevel(logging.INFO)
            request_logger.propagate = False # Чтобы не дублировать в консоль через root
            
            # Очистка старых хендлеров
            root_logger = logging.getLogger() # Для подстраховки проверяем и root
            for h in root_logger.handlers[:]:
                if isinstance(h, DiscordLogHandler):
                    root_logger.removeHandler(h)
            for h in request_logger.handlers[:]:
                request_logger.removeHandler(h)
            
            discord_handler = DiscordLogHandler(bot, settings.discord_log_channel_id)
            discord_handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(name)s: %(message)s'))
            request_logger.addHandler(discord_handler)

        try:
            async with bot:
                await bot.start(settings.discord_token)
            # Если соединение закрылось штатно, сбрасываем задержку
            logger.info("Discord bot disconnected gracefully. Resetting retry delay.")
            retry_delay = settings.discord_retry_delay
        except discord.errors.LoginFailure:
            logger.error("Critical: Invalid Discord token provided. Check your .env file.")
            # Нет смысла повторять с неверным токеном
            break
        except discord.errors.HTTPException as e:
            if e.status == 429:
                logger.error("Discord Rate Limit (429/1015). Cloudflare блокирует этот IP. "
                             "Ждем %ds перед повтором...", retry_delay)
            else:
                logger.error("Discord HTTP error: %s. Retrying in %ds...", e, retry_delay)
            # Для HTTP ошибок также используем экспоненциальную задержку
            await asyncio.sleep(retry_delay)
            retry_delay = min(retry_delay * 2, 900)  # Увеличиваем задержку до 15 минут
        except discord.ConnectionClosed as e:
            logger.error("Discord connection closed unexpectedly: Code %s - %s. Retrying in %ds...", e.code, e, retry_delay)
            await asyncio.sleep(retry_delay)
            retry_delay = min(retry_delay * 2, 900)
        except Exception as e:
            logger.error("Discord connection error: %s. Retrying in %ds...", e, retry_delay)
            await asyncio.sleep(retry_delay)
            retry_delay = min(retry_delay * 2, 900)

if __name__ == "__main__":
    asyncio.run(main())