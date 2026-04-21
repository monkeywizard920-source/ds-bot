from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class StoredMessage:
    chat_id: int
    message_id: int
    user_id: int | None
    username: str | None
    full_name: str | None
    text: str
    created_at: datetime
