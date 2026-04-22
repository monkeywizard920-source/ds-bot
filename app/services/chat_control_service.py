 from __future__ import annotations
import json
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

    async def toggle_mode(self, chat_id: int) -> str:
        settings = await self.get_status(chat_id)
        new_mode = "manual" if settings["mode"] == "ai" else "ai"
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

    async def get_all_chats_list(self) -> str:
        chat_ids = await self._repository.get_all_active_chats()
        lines = []
        for cid in chat_ids:
            s = await self._repository.get_settings(cid)
            status = "✅" if s["is_enabled"] else "❌"
            mode = "🤖" if s["mode"] == "ai" else "👤"
            lines.append(f"{status} {mode} ID: `{cid}`")
        return "\n".join(lines) or "Список пуст"

    def format_forward_header(self, chat_id: int, user_id: int | None, text: str) -> str:
        return f"[chat_id={chat_id}][user_id={user_id or 0}]\n{text}"

    def parse_reply_header(self, text: str) -> tuple[int, int] | None:
        try:
            import re
            match = re.search(r"\[chat_id=(-?\d+)\]\[user_id=(\d+)\]", text)
            if match:
                return int(match.group(1)), int(match.group(2))
        except Exception:
            pass
        return None