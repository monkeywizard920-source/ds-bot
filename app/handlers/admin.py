from __future__ import annotations
import asyncio
from aiogram import Router, Bot, F, types
from aiogram.filters import Command
from aiogram.types import Message, BufferedInputFile, InlineKeyboardButton, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from app.config import Settings
from app.services.chat_control_service import ChatControlService

router = Router(name="admin")

# Фильтр: только админ может использовать этот роутер
router.message.filter(lambda m, settings: m.from_user and m.from_user.id == settings.admin_id)

@router.message(Command("on"))
async def cmd_on(message: Message, chat_control: ChatControlService):
    await chat_control.set_enabled(message.chat.id, True)
    await message.answer("Бот включен в этом чате.")

@router.message(Command("off"))
async def cmd_off(message: Message, chat_control: ChatControlService):
    await chat_control.set_enabled(message.chat.id, False)
    await message.answer("Бот выключен.")

@router.message(Command("manual"))
async def cmd_manual(message: Message, chat_control: ChatControlService):
    await chat_control.set_mode(message.chat.id, "manual")
    await message.answer("Режим: MANUAL (Перехват сообщений).")

@router.message(Command("auto"))
async def cmd_auto(message: Message, chat_control: ChatControlService):
    await chat_control.set_mode(message.chat.id, "ai")
    await message.answer("Режим: AI (DeepSeek).")

@router.message(Command("mode"))
async def cmd_toggle(message: Message, chat_control: ChatControlService):
    mode = await chat_control.toggle_mode(message.chat.id)
    await message.answer(f"Режим изменен на: {mode.upper()}")

@router.message(Command("status"))
async def cmd_status(message: Message, chat_control: ChatControlService, settings: Settings):
    stats = await chat_control.get_system_wide_stats()
    text = (
        f"📊 Статус системы:\n"
        f"Чатов в базе: {stats['total']}\n"
        f"Отключено: {stats['disabled']}\n"
        f"Manual-режим: {stats['manual']}\n"
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

    for chat in chats:
        builder = InlineKeyboardBuilder()
        is_on = chat.get("is_enabled", True)
        mode = chat.get("mode", "ai")
        chat_id = chat["chat_id"]

        status_btn = "✅ On" if is_on else "❌ Off"
        mode_btn = "🤖 AI" if mode == "ai" else "👤 Manual"
        
        builder.row(
            InlineKeyboardButton(text=status_btn, callback_data=f"toggle_on:{chat_id}"),
            InlineKeyboardButton(text=mode_btn, callback_data=f"toggle_mode:{chat_id}")
        )
        builder.row(InlineKeyboardButton(text="📥 Export JSON", callback_data=f"export_chat:{chat_id}"))
        
        raw_title = str(chat.get("title") or "Unknown")
        chat_title = (raw_title[:30] + "...") if len(raw_title) > 30 else raw_title
        await message.answer(
            f"🔹 **{chat_title}**\n`{chat_id}`",
            reply_markup=builder.as_markup(),
            parse_mode="Markdown"
        )

@router.callback_query(F.data.startswith("toggle_on:"))
async def handle_toggle_on(callback: CallbackQuery, chat_control: ChatControlService):
    chat_id = int(callback.data.split(":")[1])
    new_val = await chat_control.toggle_enabled(chat_id)
    
    # Обновляем кнопки
    builder = InlineKeyboardBuilder()
    settings = await chat_control.get_status(chat_id)
    status_btn = "✅ On" if new_val else "❌ Off"
    mode_btn = "🤖 AI" if settings["mode"] == "ai" else "👤 Manual"
    
    builder.row(
        InlineKeyboardButton(text=status_btn, callback_data=f"toggle_on:{chat_id}"),
        InlineKeyboardButton(text=mode_btn, callback_data=f"toggle_mode:{chat_id}")
    )
    builder.row(InlineKeyboardButton(text="📥 Export JSON", callback_data=f"export_chat:{chat_id}"))
    
    await callback.message.edit_reply_markup(reply_markup=builder.as_markup())
    await callback.answer(f"Бот {'включен' if new_val else 'выключен'}")

@router.callback_query(F.data.startswith("toggle_mode:"))
async def handle_toggle_mode(callback: CallbackQuery, chat_control: ChatControlService):
    chat_id = int(callback.data.split(":")[1])
    new_mode = await chat_control.toggle_mode(chat_id)
    
    builder = InlineKeyboardBuilder()
    settings = await chat_control.get_status(chat_id)
    status_btn = "✅ On" if settings["is_enabled"] else "❌ Off"
    mode_btn = "🤖 AI" if new_mode == "ai" else "👤 Manual"
    
    builder.row(
        InlineKeyboardButton(text=status_btn, callback_data=f"toggle_on:{chat_id}"),
        InlineKeyboardButton(text=mode_btn, callback_data=f"toggle_mode:{chat_id}")
    )
    builder.row(InlineKeyboardButton(text="📥 Export JSON", callback_data=f"export_chat:{chat_id}"))
    
    await callback.message.edit_reply_markup(reply_markup=builder.as_markup())
    await callback.answer(f"Режим изменен на {new_mode.upper()}")

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
    if len(parts) < 2 or parts[1] not in ("1", "2"):
        return await message.answer("Использование:\n`/yazik 1` — Русский\n`/yazik 2` — Китайский", parse_mode="Markdown")
    
    lang_code = parts[1]
    await chat_control.set_global_language(lang_code)
    
    lang_name = "Русский" if lang_code == "1" else "Китайский"
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