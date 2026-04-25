#!/usr/bin/env python
"""Тестовый скрипт для проверки всех проблем."""

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


async def test_robin_mode():
    """Тест команды /robin."""
    settings = Settings()
    repo = MessageRepository(settings.database_path)
    await repo.init()
    
    chat_control = ChatControlService(repo)
    
    # Тест режима Robin
    await chat_control.set_robin_mode(123, True)
    assert await chat_control.get_robin_mode(123) == True
    await chat_control.set_robin_mode(123, False)
    assert await chat_control.get_robin_mode(123) == False
    print("[OK] Robin mode test passed")


async def test_chats_command():
    """Тест команды /chats."""
    settings = Settings()
    repo = MessageRepository(settings.database_path)
    await repo.init()
    
    chat_control = ChatControlService(repo)
    
    # Тест получения всех чатов
    chats = await chat_control.get_chats_with_meta()
    print(f"Found {len(chats)} chats")
    for chat in chats:
        title = chat['title'] if chat['title'] else 'Unknown'
        # Убираем специальные символы для Windows кодировки
        title = title.encode('ascii', errors='ignore').decode('ascii')
        print(f"  - {title} (ID: {chat['chat_id']})")
    print("[OK] Chats command test passed")


async def test_message_saving():
    """Тест сохранения сообщений."""
    settings = Settings()
    repo = MessageRepository(settings.database_path)
    await repo.init()
    
    from app.domain import StoredMessage
    from datetime import datetime, timezone
    
    # Тест сохранения сообщения
    message = StoredMessage(
        chat_id=123,
        message_id=1,
        user_id=5710686998,  # Admin ID
        username="test_admin",
        full_name="Test Admin",
        text="Test message",
        created_at=datetime.now(timezone.utc)
    )
    await repo.add(message)
    
    # Тест получения сообщений
    messages = await repo.recent(123, 10)
    assert len(messages) > 0
    print(f"[OK] Message saving test passed. Found {len(messages)} messages")


async def main():
    """Основная функция тестирования."""
    print("Running tests...")
    
    await test_admin_rights()
    await test_robin_mode()
    await test_chats_command()
    await test_message_saving()
    
    print("\n[OK] All tests passed!")


if __name__ == "__main__":
    asyncio.run(main())