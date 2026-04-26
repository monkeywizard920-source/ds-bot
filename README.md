# Context Discord Bot

Discord bot on `discord.py` that reads messages, stores per-channel context in SQLite, and answers participants with that context through the Groq LLM API.

## What It Can Do

- Stores chat messages per Discord channel.
- Builds a recent context window before every answer.
- Answers when:
  - someone uses `!ask question`;
  - someone replies to the bot;
  - someone mentions the bot;
  - `ANSWER_ON_EVERY_MESSAGE=true` is enabled.
- Sends system logs to Discord channel `1497682736817635590`.
- Supports `!reset_context` to clear memory for the current channel.

## Конфигурация (.env)

```env
DISCORD_TOKEN=your_discord_bot_token
GROQ_API_KEY=gsk_your_main_key
TWO_API_KEY=gsk_optional_backup_key
ADMIN_IDS=[123456789]
GROQ_MODEL=llama-3.3-70b-versatile
GROQ_BASE_URL=https://api.groq.com/openai/v1
```

## Project Structure

```text
app/
  __main__.py              # Entrypoint
  bot.py                   # Bot and dispatcher factory
  config.py                # Environment settings
  logging_config.py        # Logging setup
  handlers/
    chat.py                # Message and command handlers
  repositories/
    message_repository.py  # SQLite persistence
  services/
    context_service.py     # Context formatting and memory operations
      llm_service.py         # Groq LLM client (presents as DeepSeek)
```

## Notes

Бот работает через Groq API. В логах при запуске отображается, какой URL и какой ключ используются для запросов.
