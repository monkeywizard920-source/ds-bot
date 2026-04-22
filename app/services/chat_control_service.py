from __future__ import annotations
import json
import re
from app.repositories.message_repository import MessageRepository
from app.domain import StoredMessage

class ChatControlService:
    def __init__(self, repository: MessageRepository) -> None:
        self._repository = repository

    async def get_status(self, chat_id: int) -> dict:
        return await self._repository.get_settings(chat_id)

    async def set_enabled(self, chat_id: int, enabled: bool) -> None:
        await self._repository.update_settings(chat_id, is_enabled=enabled)

    async def set_mode(self, chat_id: int, mode: str) -> None:
        await self._repository.update_settings(chat_id, mode=mode)

    async def toggle_enabled(self, chat_id: int) -> bool:
        settings = await self.get_status(chat_id)
        new_status = not settings.get("is_enabled", True)
        await self.set_enabled(chat_id, new_status)
        return new_status

    async def toggle_mode(self, chat_id: int) -> str:
        settings = await self.get_status(chat_id)
        new_mode = "manual" if settings.get("mode") == "ai" else "ai"
        await self.set_mode(chat_id, new_mode)
        return new_mode

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
                "mode": settings.get("mode", "ai")
            })
        return result

    def format_forward_header(self, chat_id: int, user_id: int | None, text: str) -> str:
        return f"[chat_id={chat_id}][user_id={user_id or 0}]\n{text}"

    def parse_reply_header(self, text: str) -> tuple[int, int] | None:
        try:
            match = re.search(r"\[chat_id=(-?\d+)\]\[user_id=(\d+)\]", text)
            if match:
                return int(match.group(1)), int(match.group(2))
        except Exception:
            pass
        return None