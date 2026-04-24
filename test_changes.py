#!/usr/bin/env python
"""Тестовый скрипт для проверки основных изменений."""

import asyncio
from app.config import Settings
from app.repositories.message_repository import MessageRepository
from app.services.chat_control_service import ChatControlService


async def test_admin_rights():
    """Тест прав администраторов."""
    settings = Settings()
    print(f"Admin IDs: {settings.admin_ids}")
    assert 5710686998 in settings.admin_ids
    assert 5539641131 in settings.admin_ids
    print("[OK] Admin rights test passed")


async def test_chat_control_service():
    """Тест сервиса управления чатами."""
    repo = MessageRepository(settings.database_path)
    await repo.init()
    
    chat_control = ChatControlService(repo)
    
    # Тест режима Robin
    await chat_control.set_robin_mode(123, True)
    assert await chat_control.get_robin_mode(123) == True
    await chat_control.set_robin_mode(123, False)
    assert await chat_control.get_robin_mode(123) == False
    print("[OK] Chat control service test passed")


async def test_repository():
    """Тест репозитория."""
    from app.config import Settings
    settings = Settings()
    repo = MessageRepository(settings.database_path)
    await repo.init()
    
    # Тест получения всех чатов
    chats = await repo.get_all_active_chats()
    print(f"Found {len(chats)} active chats")
    
    # Тест настроек чата
    chat_settings = await repo.get_settings(123)
    assert "robin_mode" in chat_settings
    print("[OK] Repository test passed")


async def main():
    """Основная функция тестирования."""
    print("Running tests...")
    
    await test_admin_rights()
    await test_repository()
    await test_chat_control_service()
    
    print("\n[OK] All tests passed!")


if __name__ == "__main__":
    settings = Settings()
    asyncio.run(main())