from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import aiosqlite

from app.domain import StoredMessage


class MessageRepository:
    def __init__(self, database_path: Path) -> None:
        self._database_path = database_path

    async def init(self) -> None:
        self._database_path.parent.mkdir(parents=True, exist_ok=True)
        async with aiosqlite.connect(self._database_path) as db:
            await db.execute("PRAGMA journal_mode=WAL")
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS messages (
                    chat_id INTEGER NOT NULL,
                    message_id INTEGER NOT NULL,
                    user_id INTEGER,
                    username TEXT,
                    full_name TEXT,
                    text TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (chat_id, message_id)
                )
                """
            )
            await db.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_messages_chat_created
                ON messages (chat_id, created_at DESC)
                """
            )
            await db.commit()

    async def add(self, message: StoredMessage) -> None:
        async with aiosqlite.connect(self._database_path) as db:
            await db.execute(
                """
                INSERT OR REPLACE INTO messages (
                    chat_id,
                    message_id,
                    user_id,
                    username,
                    full_name,
                    text,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    message.chat_id,
                    message.message_id,
                    message.user_id,
                    message.username,
                    message.full_name,
                    message.text,
                    message.created_at.astimezone(timezone.utc).isoformat(),
                ),
            )
            await db.commit()

    async def recent(self, chat_id: int, limit: int) -> list[StoredMessage]:
        async with aiosqlite.connect(self._database_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """
                SELECT chat_id, message_id, user_id, username, full_name, text, created_at
                FROM messages
                WHERE chat_id = ?
                ORDER BY created_at DESC, message_id DESC
                LIMIT ?
                """,
                (chat_id, limit),
            )
            rows = await cursor.fetchall()

        messages = [
            StoredMessage(
                chat_id=row["chat_id"],
                message_id=row["message_id"],
                user_id=row["user_id"],
                username=row["username"],
                full_name=row["full_name"],
                text=row["text"],
                created_at=datetime.fromisoformat(row["created_at"]),
            )
            for row in rows
        ]
        messages.reverse()
        return messages

    async def clear_chat(self, chat_id: int) -> int:
        async with aiosqlite.connect(self._database_path) as db:
            cursor = await db.execute("DELETE FROM messages WHERE chat_id = ?", (chat_id,))
            await db.commit()
            return cursor.rowcount
