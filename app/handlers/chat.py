from __future__ import annotations

import re
from datetime import datetime, timezone

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.types import Message

from app.config import Settings
from app.domain import StoredMessage
from app.services.context_service import ContextService
from app.services.llm_service import LLMService

router = Router(name="chat")
SANYA_CALL_RE = re.compile(r"^\s*саня\b[\s,.:;!?-]*(.*)$", re.IGNORECASE)
_BOT_ID: int | None = None
_BOT_USERNAME: str | None = None


@router.message(Command("start"))
async def start(message: Message) -> None:
    await message.answer(
        "Привет. Я запоминаю новые сообщения в этом чате и отвечаю по ним, когда это полезно.\n\n"
        "Команды:\n"
        "Саня <вопрос> - спросить меня (например: Саня, что нового?)\n"
        "/context - показать недавний сохраненный контекст\n"
        "/reset_context - очистить контекст этого чата"
    )


@router.message(Command("context"))
async def show_context(
    message: Message,
    context_service: ContextService,
    settings: Settings,
) -> None:
    preview = await context_service.preview(message.chat.id)
    await message.answer(preview[: settings.max_reply_chars])


@router.message(Command("reset_context"))
async def reset_context(message: Message, context_service: ContextService) -> None:
    deleted = await context_service.clear(message.chat.id)
    await message.answer(f"Готово. Удалено сообщений из памяти: {deleted}.")


@router.message(Command("ask"))
async def ask(
    message: Message,
    context_service: ContextService,
    llm_service: LLMService,
    settings: Settings,
) -> None:
    await _remember_message(message, context_service, settings, bot)

    question = _text_without_command(message.text or message.caption or "", "/ask").strip()
    if not question:
        await message.answer("Напишите вопрос после команды: /ask что обсуждали?")
        return

    await _answer_with_context(
        message=message,
        question=question,
        context_service=context_service,
        llm_service=llm_service,
        settings=settings,
    )


@router.message(F.text | F.caption)
async def collect_and_maybe_answer(
    message: Message,
    bot: Bot,
    context_service: ContextService,
    llm_service: LLMService,
    settings: Settings,
) -> None:
    await _remember_message(message, context_service, settings, bot)

    should_answer = await _should_answer(message, bot, settings)
    if not should_answer:
        return

    text = message.text or message.caption or ""
    question = _remove_bot_mention(text, await _bot_username(bot)).strip()
    question = _remove_sanya_call(question).strip()
    if not question:
        question = text.strip()

    await _answer_with_context(
        message=message,
        question=question,
        context_service=context_service,
        llm_service=llm_service,
        settings=settings,
    )


async def _remember_message(
    message: Message, 
    context_service: ContextService, 
    settings: Settings,
    bot: Bot,
) -> None:
    text = message.text or message.caption or ""
    if not text.strip():
        return

    user = message.from_user
    chat = message.chat
    timestamp = _as_utc(message.date).strftime("%Y-%m-%d %H:%M:%S")

    # Формируем данные для текстового лога
    user_info = f"ID: {user.id if user else 'N/A'} | @{user.username if user else 'N/A'} ({user.full_name if user else 'Unknown'})"
    chat_link = f"https://t.me/{chat.username}" if chat.username else f"Private/ID: {chat.id}"
    chat_info = f"CHAT: {chat.title or 'Direct'} ({chat_link})"
    
    log_entry = (
        f"[{timestamp}] "
        f"{user_info} | "
        f"{chat_info} | "
        f"TEXT: {text.replace('\n', ' ')}\n"
    )

    # Отправляем лог в указанный Telegram-чат
    if settings.telegram_log_chat_id:
        try:
            await bot.send_message(chat_id=settings.telegram_log_chat_id, text=log_entry)
        except TelegramBadRequest as e:
            logger.error("Failed to send log to Telegram chat %s: %s", settings.telegram_log_chat_id, e)
    else:
        # Если чат для логов не указан, логируем в консоль (или в файл, если MESSAGE_LOG_PATH настроен)
        logger.info("MESSAGE LOG: %s", log_entry.strip())
        
    await context_service.remember(
        StoredMessage(
            chat_id=message.chat.id,
            message_id=message.message_id,
            user_id=user.id if user else None,
            username=user.username if user else None,
            full_name=user.full_name if user else None,
            text=text,
            created_at=_as_utc(message.date),
        )
    )


async def _answer_with_context(
    *,
    message: Message,
    question: str,
    context_service: ContextService,
    llm_service: LLMService,
    settings: Settings,
) -> None:
    context = await context_service.build_context(message.chat.id)
    pending = await message.answer("Секунду...")
    answer = await llm_service.answer(
        context=context,
        question=question,
        chat_title=message.chat.title,
    )
    answer_text = answer[: settings.max_reply_chars]
    try:
        await pending.edit_text(answer_text)
    except TelegramBadRequest:
        await message.answer(answer_text)


async def _should_answer(message: Message, bot: Bot, settings: Settings) -> bool:
    if settings.answer_on_every_message:
        return True

    text = message.text or message.caption or ""
    if SANYA_CALL_RE.match(text):
        return True

    bot_user = await _bot_user(bot)
    if message.reply_to_message and message.reply_to_message.from_user:
        if message.reply_to_message.from_user.id == bot_user.id:
            return True

    username = bot_user.username
    if username and f"@{username.lower()}" in (message.text or message.caption or "").lower():
        return True

    return False


async def _bot_username(bot: Bot) -> str | None:
    bot_user = await _bot_user(bot)
    return bot_user.username


async def _bot_user(bot: Bot):
    global _BOT_ID, _BOT_USERNAME
    if _BOT_ID is not None:
        class CachedBotUser:
            id = _BOT_ID
            username = _BOT_USERNAME

        return CachedBotUser()

    bot_user = await bot.me()
    _BOT_ID = bot_user.id
    _BOT_USERNAME = bot_user.username
    return bot_user


def _remove_bot_mention(text: str, username: str | None) -> str:
    if not username:
        return text

    return re.sub(rf"@{re.escape(username)}\b", "", text, flags=re.IGNORECASE)


def _text_without_command(text: str, command: str) -> str:
    if not text.startswith(command):
        return text

    parts = text.split(maxsplit=1)
    command_token = parts[0].split("@", maxsplit=1)[0]
    if command_token != command:
        return text

    return parts[1] if len(parts) == 2 else ""


def _remove_sanya_call(text: str) -> str:
    match = SANYA_CALL_RE.match(text)
    if not match:
        return text

    cleaned = match.group(1).strip()
    return cleaned or text


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
