from __future__ import annotations

import json
from app.repositories.message_repository import MessageRepository


class ChatControlService:
    def __init__(self, repository: MessageRepository) -> None:
        self._repository = repository

    async def get_status(self, chat_id: int) -> dict:
        """Получает текущие настройки чата."""
        return await self._repository.get_settings(chat_id)

    async def set_enabled(self, chat_id: int, enabled: bool) -> None:
        await self._repository.update_settings(chat_id, is_enabled=enabled)

    async def toggle_enabled(self, chat_id: int) -> bool:
        settings = await self.get_status(chat_id)
        new_status = not settings.get("is_enabled", True)
        await self.set_enabled(chat_id, new_status)
        return new_status

    async def get_global_language(self) -> str:
        """Получает глобальный язык системы."""
        settings = await self.get_status(0)  # ID 0 используется для глобальных настроек
        return settings.get("language", "1")

    async def set_global_language(self, lang_code: str) -> None:
        """Устанавливает глобальный язык системы."""
        await self._repository.update_settings(0, language=lang_code)

    async def set_robin_mode(self, chat_id: int, enabled: bool) -> None:
        """Устанавливает режим Robin для чата."""
        await self._repository.update_settings(chat_id, robin_mode=enabled)

    async def get_robin_mode(self, chat_id: int) -> bool:
        """Получает текущий режим Robin для чата."""
        settings = await self.get_status(chat_id)
        return settings.get("robin_mode", False)

    async def get_system_wide_stats(self) -> dict:
        return await self._repository.get_system_stats()

    async def get_chat_history_json(self, chat_id: int, limit: int = 1000) -> str:
        messages = await self._repository.recent(chat_id, limit)
        data = [
            {
                "message_id": m.message_id,
                "user": m.full_name or m.username,
                "text": m.text,
                "date": m.created_at.isoformat()
            } for m in messages
        ]
        return json.dumps(data, ensure_ascii=False, indent=2)

    async def get_chats_with_meta(self) -> list[dict]:
        chats = await self._repository.get_all_active_chats()
        result = []
        for c in chats:
            settings = await self.get_status(c["chat_id"])
            result.append({
                "chat_id": c["chat_id"],
                "title": c["last_title"] or f"ID: {c['chat_id']}",
                "is_enabled": settings.get("is_enabled", True),
            })
        return result