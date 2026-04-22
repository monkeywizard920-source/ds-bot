from __future__ import annotations
from aiogram import Router, Bot, F
from aiogram.filters import Command
from aiogram.types import Message, BufferedInputFile
from app.config import Settings
from app.services.chat_control_service import ChatControlService

router = Router(name="admin")

# Исправленный фильтр: берем admin_id напрямую из настроек в контексте
router.message.filter(lambda m, settings: m.from_user.id == settings.admin_id)

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
        f"Модель: `llama-3.3-70b` (DeepSeek 3.2)\n"
    )
    await message.answer(text, parse_mode="Markdown")

@router.message(Command("export"))
async def cmd_export(message: Message, chat_control: ChatControlService):
    history = await chat_control.get_chat_history_json(message.chat.id)
    file = BufferedInputFile(history.encode('utf-8'), filename=f"history_{message.chat.id}.json")
    await message.answer_document(file, caption="Экспорт последних 1000 сообщений.")

@router.message(Command("chats"))
async def cmd_chats(message: Message, chat_control: ChatControlService):
    list_text = await chat_control.get_all_chats_list()
    await message.answer(list_text, parse_mode="Markdown")

@router.message(Command("broadcast"))
async def cmd_broadcast(message: Message, bot: Bot, chat_control: ChatControlService):
    text = message.text.split(maxsplit=1)
    if len(text) < 2:
        return await message.answer("Введите текст: /broadcast <сообщение>")
    
    import asyncio
    chat_ids = await chat_control._repository.get_all_active_chats()
    count = 0
    for cid in chat_ids:
        settings = await chat_control.get_status(cid)
        if not settings["is_enabled"]: continue
        try:
            await bot.send_message(cid, text[1])
            count += 1
            await asyncio.sleep(0.05)
        except Exception: pass
    await message.answer(f"Рассылка завершена. Получили: {count} чатов.")

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