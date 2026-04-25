#!/usr/bin/env python
"""Тестовый скрипт для проверки, что бот не выключается."""

import asyncio
from app.config import Settings
from app.repositories.message_repository import MessageRepository
from app.services.chat_control_service import ChatControlService


async def test_bot_stays_enabled():
    """Тест, что бот остается включенным."""
    settings = Settings()
    repo = MessageRepository(settings.database_path)
    await repo.init()
    
    chat_control = ChatControlService(repo)
    
    # Включаем бот в чате
    await chat_control.set_enabled(123, True)
    chat_settings = await chat_control.get_status(123)
    print(f"Settings after enable: {chat_settings}")
    assert chat_settings.get("is_enabled", True) == True
    print("[OK] Bot enabled in chat")
    
    # Имитируем обработку сообщения
    await repo.update_settings(123, is_enabled=None)
    chat_settings = await chat_control.get_status(123)
    print(f"Settings after update with None: {chat_settings}")
    assert chat_settings.get("is_enabled", True) == True
    print("[OK] Bot still enabled after message processing")
    
    # Проверяем, что бот остается включенным
    chat_settings = await chat_control.get_status(123)
    print(f"Settings after multiple checks: {chat_settings}")
    assert chat_settings.get("is_enabled", True) == True
    print("[OK] Bot still enabled after multiple checks")


async def main():
    """Основная функция тестирования."""
    print("Running tests...")
    
    await test_bot_stays_enabled()
    
    print("\n[OK] All tests passed!")


if __name__ == "__main__":
    asyncio.run(main())