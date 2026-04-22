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
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS chat_settings (
                    chat_id INTEGER PRIMARY KEY,
                    is_enabled BOOLEAN DEFAULT 1,
                    mode TEXT DEFAULT 'ai'
                )
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

    async def get_settings(self, chat_id: int) -> dict:
        async with aiosqlite.connect(self._database_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute('SELECT * FROM chat_settings WHERE chat_id = ?', (chat_id,)) as cursor:
                row = await cursor.fetchone()
                return dict(row) if row else {"chat_id": chat_id, "is_enabled": True, "mode": "ai"}

    async def update_settings(self, chat_id: int, **kwargs) -> None:
        async with aiosqlite.connect(self._database_path) as db:
            keys = list(kwargs.keys())
            values = list(kwargs.values())
            set_clause = ", ".join([f"{k} = ?" for k in keys])
            placeholders = ", ".join(["?"] * len(keys))
            await db.execute(f'''
                INSERT INTO chat_settings (chat_id, {", ".join(keys)})
                VALUES (?, {placeholders})
                ON CONFLICT(chat_id) DO UPDATE SET {set_clause}
            ''', [chat_id] + values + values)
            await db.commit()

    async def get_all_active_chats(self) -> list[dict]:
        async with aiosqlite.connect(self._database_path) as db:
            db.row_factory = aiosqlite.Row
            # Получаем ID чата и самое последнее известное название из таблицы сообщений
            async with db.execute('''
                SELECT m.chat_id, 
                       (SELECT m2.full_name FROM messages m2 WHERE m2.chat_id = m.chat_id ORDER BY m2.created_at DESC LIMIT 1) as last_title
                FROM messages m
                GROUP BY m.chat_id
            ''') as cursor:
                rows = await cursor.fetchall()
                return [dict(r) for r in rows]

    async def get_system_stats(self) -> dict:
        async with aiosqlite.connect(self._database_path) as db:
            async with db.execute('SELECT COUNT(*), SUM(CASE WHEN is_enabled=0 THEN 1 ELSE 0 END), SUM(CASE WHEN mode="manual" THEN 1 ELSE 0 END) FROM chat_settings') as cursor:
                row = await cursor.fetchone()
                return {"total": row[0] or 0, "disabled": row[1] or 0, "manual": row[2] or 0}
