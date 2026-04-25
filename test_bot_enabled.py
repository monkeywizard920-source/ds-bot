#!/usr/bin/env python
"""Тестовый скрипт для проверки, что бот не выключается."""

import asyncio
from app.config import Settings
from app.repositories.message_repository import MessageRepository
from app.services.chat_control_service import ChatControlService


async def test_bot_enabled():
    """Тест, что бот остается включенным."""
    settings = Settings()
    repo = MessageRepository(settings.database_path)
    await repo.init()
    
    chat_control = ChatControlService(repo)
    
    # Включаем бот в чате
    await chat_control.set_enabled(123, True)
    settings = await chat_control.get_status(123)
    assert settings.get("is_enabled", True) == True
    print("[OK] Bot enabled in chat")
    
    # Проверяем, что бот остается включенным
    settings = await chat_control.get_status(123)
    assert settings.get("is_enabled", True) == True
    print("[OK] Bot still enabled in chat")


async def main():
    """Основная функция тестирования."""
    print("Running tests...")
    
    await test_bot_enabled()
    
    print("\n[OK] All tests passed!")


if __name__ == "__main__":
    asyncio.run(main())