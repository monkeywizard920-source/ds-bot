# Context Telegram Bot

Telegram bot on `aiogram` that reads messages delivered to it, stores per-chat context in SQLite, and answers participants with that context through an OpenAI-compatible LLM API.

## What It Can Do

- Stores chat messages per Telegram chat.
- Builds a recent context window before every answer.
- Answers when:
  - someone uses `/ask question`;
  - someone replies to the bot;
  - someone mentions the bot by username;
  - `ANSWER_ON_EVERY_MESSAGE=true` is enabled.
- Supports `/context` to inspect recent stored context.
- Supports `/reset_context` to clear memory for the current chat.

Telegram bots cannot read old chat history. They only receive new messages delivered after the bot joins the chat. In groups, disable privacy mode in BotFather if you want the bot to parse regular messages that are not commands, mentions, or replies.

## Setup

```bash
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .
copy .env.example .env
```

Edit `.env` and set `BOT_TOKEN` and `OPENAI_API_KEY`.

Run:

```bash
python -m app
```

If your network cannot reach `api.telegram.org`, set a proxy:

```env
TELEGRAM_PROXY_URL=http://127.0.0.1:7890
```

The proxy can also be `socks5://host:port`. To rotate proxies, put one proxy per line into `proxies.txt`.

You can also use another Telegram Bot API endpoint:

```env
TELEGRAM_API_BASE_URL=https://your-telegram-bot-api-mirror.example
```

For the official self-hosted `telegram-bot-api` server, this is usually `http://127.0.0.1:8081`.

To quickly test proxies:

```bash
python tools/check_proxies.py --limit 30 --timeout 5
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
    llm_service.py         # OpenAI-compatible LLM client
```

## Notes

The default model is `deepseek-chat` with `https://api.deepseek.com`.
For another OpenAI-compatible provider, change `OPENAI_BASE_URL`, `OPENAI_MODEL`, and set `OPENAI_API_KEY`.
The bot can rotate through LLM models using `LLM_MODELS`, comma-separated.
