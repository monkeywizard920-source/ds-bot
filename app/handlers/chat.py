from __future__ import annotations

import logging
import re
from datetime import datetime, timezone

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.types import Message

from app.config import Settings
from app.domain import StoredMessage
from app.services.chat_control_service import ChatControlService
from app.services.context_service import ContextService
from app.services.llm_service import LLMService

logger = logging.getLogger(__name__)
router = Router(name="chat")
SANYA_CALL_RE = re.compile(r"^\s*саня\b[\s,.:;!?-]*(.*)$", re.IGNORECASE)

_BOT_ID: int | None = None
_BOT_USERNAME: str | None = None

@router.message.middleware()
async def chat_guard(handler, event: Message, data):
    """Глобальный фильтр состояния чата (ВКЛ/ВЫКЛ/MANUAL)."""
    chat_control: ChatControlService = data.get('chat_control')
    
    if not event.from_user:
        return await handler(event, data)

    if chat_control:
        chat_settings = await chat_control.get_status(event.chat.id)
        # Блокируем ТОЛЬКО если статус явно равен False (0 в БД). 
        # Если там None или True — продолжаем работу.
        if chat_settings.get("is_enabled") is False:
            return

    return await handler(event, data)


@router.message(Command("context"))
async def show_context(
    message: Message,
    context_service: ContextService,
    settings: Settings,
) -> None:
    preview = await context_service.preview(message.chat.id)
    await message.answer(preview[: settings.max_reply_chars])


@router.message(Command("robin"))
async def toggle_robin_mode(
    message: Message,
    chat_control: ChatControlService,
) -> None:
    current_mode = await chat_control.get_global_robin_mode()
    new_mode = not current_mode
    await chat_control.set_global_robin_mode(new_mode)
    
    status = "ВКЛЮЧЕН глобально (отвечаю на всё во всех чатах)" if new_mode else "ВЫКЛЮЧЕН (отвечаю на упоминания)"
    await message.answer(f"📢 Режим Robin: {status}")


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
    should_answer = await _should_answer(message, bot, settings, chat_control)
    if not should_answer:
        logger.debug(f"Should not answer in chat {message.chat.id}")
        return

    text = message.text or message.caption or ""
    question = _remove_bot_mention(text, await _bot_username(bot)).strip()
    question = _remove_sanya_call(question).strip()
    if not question:
        question = text.strip()

    logger.debug(f"Answering in chat {message.chat.id}")
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
    """Сохраняет сообщение в контексте и логирует его."""
    # Регистрируем чат в базе (без изменения статуса ВКЛ/ВЫКЛ)
    await context_service._repository.update_settings(message.chat.id)
    
    # Проверяем, нужно ли сохранять сообщение
    user = message.from_user
    if not user:
        return

    text = message.text or message.caption or ""
    if not text.strip():
        return
    
    user_id = user.id
    
    # Логируем сообщение (кроме администраторов и исключенных пользователей)
    if user_id not in settings.admin_ids and user_id not in settings.excluded_ids:
        await _log_message(message, settings, bot)
    
    # Сохраняем сообщение в контексте (включая администраторов)
    await context_service.remember(
        StoredMessage(
            chat_id=message.chat.id,
            message_id=message.message_id,
            user_id=user_id,
            username=user.username,
            full_name=user.full_name,
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
    """Генерирует и отправляет ответ на сообщение."""
    if not message.from_user:
        return
    
    context = await context_service.build_context(message.chat.id)
    global_lang = await chat_control.get_global_language()
    is_admin = message.from_user.id in settings.admin_ids

    pending = await message.answer("Секунду...")
    try:
        answer = await llm_service.answer(
            context=context,
            question=question,
            chat_title=message.chat.title,
            language=global_lang,
            is_admin=is_admin
        )
        answer_text = answer[: settings.max_reply_chars]
        await pending.edit_text(answer_text)
    except TelegramBadRequest:
        await message.answer(answer[: settings.max_reply_chars])
    except Exception as e:
        logger.error("Ошибка при генерации ответа: %s", e)
        await message.answer("Извините, произошла ошибка при генерации ответа.")


async def _should_answer(
    message: Message, 
    bot: Bot, 
    settings: Settings,
    chat_control: ChatControlService,
) -> bool:
    """Определяет, должен ли бот отвечать на сообщение."""
    # Не отвечаем на команды
    if message.text and message.text.startswith('/'):
        return False
    
    # Проверка глобального режима Robin
    if await chat_control.get_global_robin_mode():
        return True

    # Глобальный режим ответа на все сообщения
    if settings.answer_on_every_message:
        return True

    text = message.text or message.caption or ""
    
    # Ответ на обращение "Саня"
    if SANYA_CALL_RE.match(text):
        return True

    # Ответ на сообщение, адресованное боту
    if message.reply_to_message and message.reply_to_message.from_user:
        if message.reply_to_message.from_user.id == (await _bot_user(bot)).id:
            return True
    
    # Ответ на упоминание бота
    bot_username = await _bot_username(bot)
    if bot_username and f"@{bot_username.lower()}" in text.lower():
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


async def _log_message(message: Message, settings: Settings, bot: Bot) -> None:
    """Логирует сообщение в консоль и Telegram-чат."""
    user = message.from_user
    chat = message.chat
    text = message.text or message.caption or ""
    
    if not user or user.id in settings.admin_ids or user.id in settings.excluded_ids:
        return
    
    timestamp = _as_utc(message.date).strftime("%Y-%m-%d %H:%M:%S")
    user_info = f"ID: {user.id} | @{user.username if user.username else 'N/A'} ({user.full_name})"
    chat_link = f"https://t.me/{chat.username}" if chat.username else f"Private/ID: {chat.id}"
    chat_info = f"CHAT: {chat.title or 'Direct'} ({chat_link})"
    text_single_line = text.replace("\n", " ")
    log_entry = (
        f"[{timestamp}] "
        f"{user_info} | "
        f"{chat_info} | "
        f"TEXT: {text_single_line}\n"
    )
    
    logger.info("LOG: %s", log_entry.strip())
    
    if settings.telegram_log_chat_id:
        try:
            await bot.send_message(chat_id=settings.telegram_log_chat_id, text=log_entry)
        except Exception as e:
            logger.error("Failed to send log to Telegram chat %s: %s", settings.telegram_log_chat_id, e)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
