import logging
import re
from datetime import datetime, timezone
import discord
from discord.ext import commands
from app.domain import StoredMessage

logger = logging.getLogger(__name__)
# Специальный логгер только для запросов пользователей в Discord канал
request_logger = logging.getLogger("discord_request_log")
ORION_CALL_RE = re.compile(r"^\s*(orion|orionis|орион|орионис)\b[\s,.:;!?-]*(.*)$", re.IGNORECASE)

class DiscordLogHandler(logging.Handler):
    """Отправляет логи уровня INFO и выше в указанный канал Discord."""
    def __init__(self, bot: commands.Bot, channel_id: int):
        super().__init__()
        self.bot = bot
        self.channel_id = channel_id
        self.setLevel(logging.INFO)

    def emit(self, record):
        if not self.bot.is_ready():
            return
        log_entry = self.format(record)
        # Отрезаем имя логгера из сообщения для красоты
        msg = log_entry.split(":", 1)[-1].strip() if ":" in log_entry else log_entry
        self.bot.loop.create_task(self.send_log(log_entry))

    async def send_log(self, message: str):
        channel = self.bot.get_channel(self.channel_id)
        if channel:
            await channel.send(f"📝 **Log:** {message[:1950]}")

def setup_discord_handlers(bot: commands.Bot):
    settings = bot.settings

    def is_admin():
        async def predicate(ctx):
            # Проверка: ID автора сообщения должен быть в списке ADMIN_IDS из конфига
            return ctx.author.id in settings.admin_ids
        return commands.check(predicate)

    @bot.event
    async def on_ready():
        logger.info(f"Logged in as {bot.user} (ID: {bot.user.id})")
        logger.info(f"Loaded Admin IDs: {settings.admin_ids}")
        logger.info(f"Active Command Prefix: {bot.command_prefix}")

    @bot.event
    async def on_command_error(ctx, error):
        """Обработка ошибок команд (чтобы не было 'тихого' игнорирования)."""
        if isinstance(error, commands.CheckFailure):
            await ctx.reply("⛔ У вас нет прав администратора для этой команды.")
            logger.warning(f"User {ctx.author} (ID: {ctx.author.id}) tried to use admin command: {ctx.command}")
        elif isinstance(error, commands.CommandNotFound):
            pass # Игнорируем, если команда не найдена
        else:
            logger.error(f"Command Error in {ctx.command}: {error}")
            await ctx.reply(f"❌ Ошибка: {error}")

    @bot.event
    async def on_message(message: discord.Message):
        if message.author.bot:
            return

        # Проверяем, включен ли бот в канале
        chat_settings = await bot.chat_control.get_status(message.channel.id)
        is_admin_user = message.author.id in settings.admin_ids
        
        if chat_settings.get("is_enabled") is False and not is_admin_user:
            # Если бот выключен, проверяем только на команду включения
            if not message.content.startswith(f"{bot.command_prefix}on"):
                return

        # Сохраняем сообщение в историю
        await bot.context_service._repository.update_settings(message.channel.id)
        await bot.context_service.remember(
            StoredMessage(
                chat_id=message.channel.id,
                message_id=message.id,
                user_id=message.author.id,
                username=message.author.name,
                full_name=message.author.display_name,
                text=message.content,
                created_at=message.created_at.replace(tzinfo=timezone.utc),
            )
        )

        # Логирование запроса
        if not is_admin_user:
            log_msg = f"[{message.channel}] {message.author}: {message.content}"
            logger.info(log_msg)
            # Отправляем только это в Discord канал логов
            request_logger.info(log_msg)

        # Проверка, нужно ли отвечать
        await bot.process_commands(message)
        
        # Если это не команда, проверяем условия для ответа LLM
        if not message.content.startswith(bot.command_prefix):
            should_answer = await _should_answer_discord(message, bot)
            if should_answer:
                await _answer_discord(message, bot)

    @bot.command(name="say")
    @is_admin()
    async def cmd_say(ctx, channel: discord.TextChannel = None, *, text: str):
        """Отправить сообщение от имени бота в указанный канал."""
        target = channel or ctx.channel
        await target.send(text)
        if channel: # Если писали в другой канал, подтверждаем выполнение
            await ctx.message.add_reaction("✅")

    # --- Команды Администратора ---

    @bot.command(name="off")
    @is_admin()
    async def cmd_off(ctx, target_id: int = None):
        channel_id = target_id or ctx.channel.id
        await bot.chat_control.set_enabled(channel_id, is_enabled=False)
        await ctx.send(f"❌ Бот выключен в канале `{channel_id}`")

    @bot.command(name="on")
    @is_admin()
    async def cmd_on(ctx, target_id: int = None):
        channel_id = target_id or ctx.channel.id
        await bot.chat_control.set_enabled(channel_id, is_enabled=True)
        await ctx.send(f"✅ Бот включен в канале `{channel_id}`")

    @bot.command(name="robin")
    @is_admin()
    async def cmd_robin(ctx):
        current_mode = await bot.chat_control.get_global_robin_mode()
        new_mode = not current_mode
        await bot.chat_control.set_global_robin_mode(new_mode)
        status = "ВКЛЮЧЕН глобально" if new_mode else "ВЫКЛЮЧЕН"
        await ctx.send(f"📢 Режим Robin: {status}")

    @bot.command(name="status")
    @is_admin()
    async def cmd_status(ctx):
        stats = await bot.chat_control.get_system_wide_stats()
        text = (
            f"📊 **Статус системы:**\n"
            f"Каналов в базе: {stats['total']}\n"
            f"Отключено: {stats['disabled']}\n"
            f"Модель: `{settings.groq_model}`\n"
        )
        await ctx.send(text)

    @bot.command(name="yazik")
    @is_admin()
    async def cmd_language(ctx, lang_code: str):
        if lang_code not in ("1", "2", "3"):
            return await ctx.send("1-RU, 2-CH, 3-UA")
        await bot.chat_control.set_global_language(lang_code)
        await ctx.send(f"Глобальный язык изменен на код: {lang_code}")

    @bot.command(name="giveadmin")
    @is_admin()
    async def cmd_give_admin(ctx, member: discord.Member):
        """Назначить пользователя администратором бота (временно, до перезагрузки)."""
        if member.id not in settings.admin_ids:
            settings.admin_ids.append(member.id)
            await ctx.send(f"✅ {member.mention} теперь администратор бота.")
            logger.info(f"User {member} (ID: {member.id}) promoted to admin by {ctx.author}")
        else:
            await ctx.send(f"ℹ️ {member.mention} уже является администратором.")

    @bot.command(name="removeadmin")
    @is_admin()
    async def cmd_remove_admin(ctx, member: discord.Member):
        """Удалить пользователя из списка администраторов бота."""
        creator_id = 1365594992193830912
        if member.id == creator_id:
            return await ctx.send("❌ Нельзя забрать права у создателя бота.")

        if member.id in settings.admin_ids:
            settings.admin_ids.remove(member.id)
            await ctx.send(f"✅ {member.mention} больше не администратор бота.")
            logger.info(f"User {member} (ID: {member.id}) demoted from admin by {ctx.author}")
        else:
            await ctx.send(f"ℹ️ {member.mention} не является администратором.")

    # --- Обычные команды ---

    @bot.command(name="reset_context")
    async def reset_context(ctx):
        deleted = await bot.context_service.clear(ctx.channel.id)
        await ctx.send(f"Память очищена. Удалено сообщений: {deleted}")

    @bot.command(name="ask")
    async def ask(ctx, *, question: str):
        await _answer_discord(ctx.message, bot, question)

async def _should_answer_discord(message: discord.Message, bot: commands.Bot) -> bool:
    # 1. Глобальный Robin
    if await bot.chat_control.get_global_robin_mode():
        return True
    
    # 2. Глобальная настройка
    if bot.settings.answer_on_every_message:
        return True

    # 3. Обращение по имени
    if ORION_CALL_RE.match(message.content):
        return True

    # 4. Упоминание бота
    if bot.user.mentioned_in(message):
        return True

    # 5. Ответ на сообщение бота
    if message.reference:
        try:
            ref_msg = await message.channel.fetch_message(message.reference.message_id)
            if ref_msg.author.id == bot.user.id:
                return True
        except: pass

    return False

async def _answer_discord(message: discord.Message, bot: commands.Bot, override_question: str = None):
    # Очистка текста от упоминаний и имени бота
    question = override_question or message.content
    if not override_question:
        question = re.sub(rf'<@!?{bot.user.id}>', '', question).strip()
        match = ORION_CALL_RE.match(question)
        if match:
            question = match.group(1).strip() or question

    if not question:
        return

    context = await bot.context_service.build_context(message.channel.id)
    global_lang = await bot.chat_control.get_global_language()
    is_admin = message.author.id in bot.settings.admin_ids

    # Эмуляция печатания
    async with message.channel.typing():
        try:
            answer = await bot.llm_service.answer(
                context=context,
                question=question,
                chat_title=str(message.channel),
                language=global_lang,
                is_admin=is_admin
            )
            
            # В Discord лимит 2000 символов на сообщение
            if len(answer) > 2000:
                chunks = [answer[i:i+2000] for i in range(0, len(answer), 2000)]
                for chunk in chunks:
                    await message.reply(chunk)
            else:
                await message.reply(answer)
        except Exception as e:
            logger.error("LLM Error: %s", e)
            await message.channel.send("❌ Ошибка генерации.")