from __future__ import annotations

import logging
import re
from datetime import datetime, timezone

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.filters import Command
from aiogram.types import Message

from app.config import Settings
from app.domain import StoredMessage
from app.services.context_service import ContextService
from app.services.llm_service import LLMService
from app.services.chat_control_service import ChatControlService

logger = logging.getLogger(__name__)
router = Router(name="chat")
SANYA_CALL_RE = re.compile(r"^\s*саня\b[\s,.:;!?-]*(.*)$", re.IGNORECASE)

_BOT_ID: int | None = None
_BOT_USERNAME: str | None = None

@router.message.middleware()
async def chat_guard(handler, event: Message, data):
    """Глобальный фильтр состояния чата (ВКЛ/ВЫКЛ/MANUAL)."""
    chat_control: ChatControlService = data['chat_control']
    settings: Settings = data['settings']
    
    # 1. Если пользователь в списке исключений или админ — пропускаем без ограничений (manual mode и т.д.)
    uid = event.from_user.id if event.from_user else None
    if uid and (int(uid) in [int(i) for i in settings.excluded_ids] or int(uid) == int(settings.admin_id)):
        return await handler(event, data)

    if not event.from_user:
        return await handler(event, data)

    chat_settings = await chat_control.get_status(event.chat.id)
    
    # 1. Если бот выключен — полный игнор
    if not chat_settings.get("is_enabled", True):
        return

    # 2. Если ручной режим — пересылка админу и остановка (команды пропускаем)
    if chat_settings.get("mode") == "manual" and not (event.text or "").startswith("/"):
        bot: Bot = data['bot']
        log_text = chat_control.format_forward_header(
            event.chat.id, event.from_user.id, event.text or event.caption or "[Медиа]"
        )
        await bot.send_message(settings.admin_id, log_text)
        return

    return await handler(event, data)


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
    bot: Bot,
    context_service: ContextService,
    llm_service: LLMService,
    chat_control: ChatControlService,
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
        chat_control=chat_control,
        settings=settings,
    )


@router.message(F.text | F.caption)
async def collect_and_maybe_answer(
    message: Message,
    bot: Bot,
    context_service: ContextService,
    llm_service: LLMService,
    chat_control: ChatControlService,
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
        chat_control=chat_control,
        settings=settings,
    )


async def _remember_message(
    message: Message, 
    context_service: ContextService, 
    settings: Settings,
    bot: Bot,
) -> None:
    # Проверяем, нужно ли игнорировать сообщение
    uid = message.from_user.id if message.from_user else None
    if uid and (uid in settings.excluded_ids or uid == settings.admin_id):
        return

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

    # Всегда логируем в консоль для отладки
    logger.info("LOG: %s", log_entry.strip())

    # Отправляем лог в указанный Telegram-чат
    if settings.telegram_log_chat_id:
        try:
            await bot.send_message(chat_id=settings.telegram_log_chat_id, text=log_entry)
        except Exception as e:
            logger.error("Failed to send log to Telegram chat %s: %s", settings.telegram_log_chat_id, e)
        
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
    chat_control: ChatControlService,
    settings: Settings,
) -> None:
    context = await context_service.build_context(message.chat.id)
    global_lang = await chat_control.get_global_language()
    pending = await message.answer("Секунду...")
    answer = await llm_service.answer(
        context=context,
        question=question,
        chat_title=message.chat.title,
        language=global_lang
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

    if message.reply_to_message and message.reply_to_message.from_user:
        if message.reply_to_message.from_user.id == bot.id:
            return True

    bot_user = await _bot_user(bot)
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
