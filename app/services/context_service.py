from __future__ import annotations

from datetime import timezone

from app.domain import StoredMessage
from app.repositories.message_repository import MessageRepository


class ContextService:
    def __init__(
        self,
        repository: MessageRepository,
        max_context_messages: int,
        max_context_chars: int,
    ) -> None:
        self._repository = repository
        self._max_context_messages = max_context_messages
        self._max_context_chars = max_context_chars

    async def remember(self, message: StoredMessage) -> None:
        text = message.text.strip()
        if not text:
            return
        await self._repository.add(message)

    async def clear(self, chat_id: int) -> int:
        return await self._repository.clear_chat(chat_id)

    async def build_context(self, chat_id: int) -> str:
        messages = await self._repository.recent(chat_id, self._max_context_messages)
        if not messages:
            return ""

        return self._join_with_limit(messages)

    async def preview(self, chat_id: int, limit: int = 12) -> str:
        messages = await self._repository.recent(chat_id, min(limit, self._max_context_messages))
        if not messages:
            return "Пока нет сохраненных сообщений."

        return self._join_with_limit(messages)

    @staticmethod
    def _format_message(message: StoredMessage) -> str:
        author = message.full_name or message.username or "Unknown"
        if message.username:
            author = f"{author} (@{message.username})"

        created_at = message.created_at.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        return f"[{created_at}] {author}: {message.text}"

    def _join_with_limit(self, messages: list[StoredMessage]) -> str:
        lines: list[str] = []
        total = 0
        for message in reversed(messages):
            line = self._format_message(message)
            added = len(line) + (1 if lines else 0)
            if total + added > self._max_context_chars:
                break
            lines.append(line)
            total += added

        lines.reverse()
        return "\n".join(lines)
