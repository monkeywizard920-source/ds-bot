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

## Project Structure

```text
app/
  __main__.py              # Entrypoint
  config.py                # Environment settings
  logging_config.py        # Logging setup
  discord_handlers.py      # Discord events and commands
  repositories/
    message_repository.py  # SQLite persistence
  services/
    context_service.py     # Context formatting and memory operations
    llm_service.py         # Groq LLM client
    chat_control_service.py # Chat settings and control
```

## Notes

Бот работает через Groq API. В логах при запуске отображается, какой URL и какой ключ используются для запросов.
