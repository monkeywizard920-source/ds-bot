#!/usr/bin/env python
"""Тестовый скрипт для проверки исправлений."""

import asyncio
from app.config import Settings
from app.repositories.message_repository import MessageRepository
from app.services.chat_control_service import ChatControlService


async def test_robin_command():
    """Тест команды /robin."""
    settings = Settings()
    repo = MessageRepository(settings.database_path)
    await repo.init()
    
    chat_control = ChatControlService(repo)
    
    # Тест переключения режима Robin
    await chat_control.set_robin_mode(123, True)
    assert await chat_control.get_robin_mode(123) == True
    print("[OK] Robin mode enabled")
    
    await chat_control.set_robin_mode(123, False)
    assert await chat_control.get_robin_mode(123) == False
    print("[OK] Robin mode disabled")


async def test_chats_command():
    """Тест команды /chats."""
    settings = Settings()
    repo = MessageRepository(settings.database_path)
    await repo.init()
    
    chat_control = ChatControlService(repo)
    
    # Тест получения всех чатов
    chats = await chat_control.get_chats_with_meta()
    print(f"[OK] Found {len(chats)} chats")
    
    # Группируем чаты
    group_chats = [c for c in chats if c["chat_id"] < 0]
    private_chats = [c for c in chats if c["chat_id"] > 0]
    
    print(f"[OK] Group chats: {len(group_chats)}")
    print(f"[OK] Private chats: {len(private_chats)}")


async def main():
    """Основная функция тестирования."""
    print("Running tests...")
    
    await test_robin_command()
    await test_chats_command()
    
    print("\n[OK] All tests passed!")


if __name__ == "__main__":
    asyncio.run(main())