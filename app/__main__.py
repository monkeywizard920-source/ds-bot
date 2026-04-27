from __future__ import annotations

import asyncio
import logging
import os
import discord
from discord.ext import commands
from aiohttp import web

from app.config import Settings, logger as config_logger
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
    # Railway/Render передают PORT автоматически
    port = int(os.environ.get("PORT", 8080))
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

    bot = commands.Bot(command_prefix=settings.command_prefix, intents=intents)
    bot.settings = settings
    bot.context_service = context_service
    bot.llm_service = llm_service
    bot.chat_control = chat_control
    setup_discord_handlers(bot)

    if settings.discord_log_channel_id:
        from app.discord_handlers import DiscordLogHandler
        request_logger = logging.getLogger("discord_request_log")
        request_logger.setLevel(logging.INFO)
        request_logger.propagate = False
        
        discord_handler = DiscordLogHandler(bot, settings.discord_log_channel_id)
        discord_handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(name)s: %(message)s'))
        request_logger.addHandler(discord_handler)

    logger.info("Starting Discord bot...")
    try:
        async with bot:
            await bot.start(settings.discord_token)
    except Exception as e:
        logger.error("Critical error starting Discord bot: %s", e)

if __name__ == "__main__":
    asyncio.run(main())