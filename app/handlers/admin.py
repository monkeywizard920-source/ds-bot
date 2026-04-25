from __future__ import annotations

import asyncio
import logging
from aiogram import Bot, F, Router
from aiogram.filters import BaseFilter, Command
from aiogram.types import BufferedInputFile, CallbackQuery, InlineKeyboardButton, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.config import Settings
from app.services.chat_control_service import ChatControlService

logger = logging.getLogger(__name__)

router = Router(name="admin")

class AdminFilter(BaseFilter):
    """Проверка, что пользователь является администратором."""
    async def __call__(self, message: Message, settings: Settings) -> bool:
        if not message.from_user:
            return False
        user_id = message.from_user.id
        # Логируем проверку администраторов для отладки
        logger.info(f"Checking admin rights for user {user_id}. Admins: {settings.admin_ids}")
        return user_id in settings.admin_ids

# Применяем фильтр ко всем хендлерам в этом роутере
router.message.filter(AdminFilter())

@router.message(Command("off"))
async def cmd_off(message: Message, chat_control: ChatControlService):
    parts = (message.text or "").split()
    target_id = message.chat.id
    if len(parts) > 1:
        try:
            target_id = int(parts[1])
        except ValueError:
            return await message.answer("ID чата должен быть числом.")
    
    await chat_control.set_enabled(target_id, is_enabled=False)
    await message.answer(f"❌ Бот выключен в чате `{target_id}`", parse_mode="Markdown")

@router.message(Command("on"))
async def cmd_on(message: Message, chat_control: ChatControlService):
    parts = (message.text or "").split()
    target_id = message.chat.id
    if len(parts) > 1:
        try:
            target_id = int(parts[1])
        except ValueError:
            return await message.answer("ID чата должен быть числом.")
    
    await chat_control.set_enabled(target_id, is_enabled=True)
    await message.answer(f"✅ Бот включен в чате `{target_id}`", parse_mode="Markdown")

@router.message(Command("status"))
async def cmd_status(message: Message, chat_control: ChatControlService, settings: Settings):
    stats = await chat_control.get_system_wide_stats()
    text = (
        f"📊 Статус системы:\n"
        f"Чатов в базе: {stats['total']}\n"
        f"Отключено: {stats['disabled']}\n"
        f"Модель: `{settings.groq_model}` (DeepSeek 3.2)\n"
    )
    await message.answer(text, parse_mode="Markdown")

@router.message(Command("export"))
async def cmd_export(message: Message, chat_control: ChatControlService):
    history = await chat_control.get_chat_history_json(message.chat.id)
    file = BufferedInputFile(history.encode('utf-8'), filename=f"history_{message.chat.id}.json")
    await message.answer_document(file, caption="Экспорт последних 1000 сообщений.")

@router.message(Command("chats"))
async def cmd_chats(message: Message, chat_control: ChatControlService):
    chats = await chat_control.get_chats_with_meta()
    if not chats:
        return await message.answer("Список чатов пуст.")

    # Группируем чаты по типам
    group_chats = [c for c in chats if c["chat_id"] < 0]
    private_chats = [c for c in chats if c["chat_id"] > 0]
    
    response = "📋 **Список чатов:**\n\n"
    
    # Групповые чаты
    if group_chats:
        response += "👥 *Групповые чаты:*\n"
        for chat in group_chats[:10]:  # Ограничиваем количество групповых чатов
            is_on = chat.get("is_enabled", True)
            status_emoji = "✅" if is_on else "❌"
            chat_title = chat.get("title", "Unknown") or f"ID: {chat['chat_id']}"
            response += f"{status_emoji} `{chat['chat_id']}` - {chat_title}\n"
    
    # Личные чаты
    if private_chats:
        response += "\n👤 *Личные чаты:*\n"
        for chat in private_chats[:5]:  # Ограничиваем количество личных чатов
            chat_title = chat.get("title", "Unknown") or f"ID: {chat['chat_id']}"
            response += f"🔹 `{chat['chat_id']}` - {chat_title}\n"
    
    # Если есть еще чаты
    total_chats = len(chats)
    if total_chats > 15:
        response += f"\n📊 *Всего чатов:* {total_chats} (показано 15)"
    
    await message.answer(response, parse_mode="Markdown")

@router.callback_query(F.data.startswith("export_chat:"))
async def handle_export_callback(callback: CallbackQuery, chat_control: ChatControlService):
    chat_id = int(callback.data.split(":")[1])
    history = await chat_control.get_chat_history_json(chat_id)
    file = BufferedInputFile(history.encode('utf-8'), filename=f"history_{chat_id}.json")
    await callback.message.answer_document(file, caption=f"Экспорт чата `{chat_id}`")
    await callback.answer()

@router.message(Command("say"))
async def cmd_say(message: Message, bot: Bot):
    parts = (message.text or "").split(maxsplit=2)
    if len(parts) < 3:
        return await message.answer("Формат: `/say <chat_id> <текст>`", parse_mode="Markdown")
    
    try:
        target_chat_id = int(parts[1].strip())
        text_to_send = parts[2]
        await bot.send_message(target_chat_id, text_to_send)
        try:
            await message.react([{"type": "emoji", "emoji": "💬"}])
        except Exception:
            await message.answer("✅ Отправлено")
    except Exception as e:
        await message.answer(f"Ошибка: {e}")

@router.message(Command("broadcast"))
async def cmd_broadcast(message: Message, bot: Bot, chat_control: ChatControlService):
    text_parts = (message.text or "").split(maxsplit=1)
    if len(text_parts) < 2:
        return await message.answer("Введите текст: /broadcast <сообщение>")
    
    chats_meta = await chat_control.get_chats_with_meta()
    count = 0
    for chat in chats_meta:
        if not chat["is_enabled"]:
            continue
        chat_id = chat["chat_id"]
        try:
            await bot.send_message(chat_id, text_parts[1])
            count += 1
            await asyncio.sleep(0.05)
        except Exception: pass
    await message.answer(f"Рассылка завершена. Получили: {count} чатов.")

@router.message(Command("yazik"))
async def cmd_language(message: Message, chat_control: ChatControlService):
    parts = (message.text or "").split()
    if len(parts) < 2 or parts[1] not in ("1", "2", "3"):
        return await message.answer(
            "Использование:\n`/yazik 1` — Русский\n`/yazik 2` — Китайский\n`/yazik 3` — Украинский",
            parse_mode="Markdown"
        )
    
    lang_code = parts[1]
    await chat_control.set_global_language(lang_code)
    
    languages = {"1": "Русский", "2": "Китайский", "3": "Украинский"}
    lang_name = languages.get(lang_code, "Неизвестный")
    
    await message.answer(f"Глобальный язык изменен на: **{lang_name}**", parse_mode="Markdown")

# Безопасный фильтр для ответов админа (проверяет и текст, и подписи к фото)
@router.message(
    F.reply_to_message & 
    (F.reply_to_message.text | F.reply_to_message.caption).regexp(r"\[chat_id=(-?\d+)\]")
)
async def admin_reply_handler(message: Message, bot: Bot, chat_control: ChatControlService):
    header_text = message.reply_to_message.text or message.reply_to_message.caption
    if not header_text: return
    
    target = chat_control.parse_reply_header(header_text)
    if not target: return
    
    chat_id, _ = target
    try:
        if message.text:
            await bot.send_message(chat_id, message.text)
        elif message.photo:
            await bot.send_photo(chat_id, message.photo[-1].file_id, caption=message.caption)
        await message.react([{"type": "emoji", "emoji": "✅"}])
    except Exception as e:
        await message.answer(f"Ошибка отправки: {e}")