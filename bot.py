import os
import asyncio
import logging
from collections import deque
from datetime import datetime
from urllib.parse import urlparse

import pytz
from telegram import Update
from telegram.ext import (
    Application,
    ApplicationBuilder,
    AIORateLimiter,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# -------------------- ЛОГИ --------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
log = logging.getLogger("lead-counter-bot")

# -------------------- ENV --------------------
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
CHAT_ID = int(os.getenv("CHAT_ID", "0").strip() or "0")
TZ_NAME = os.getenv("TIMEZONE", "America/Los_Angeles").strip()
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "").strip()  # например: https://lead-counter-bot-production.up.railway.app/hook-1111

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is required")
if not CHAT_ID:
    raise RuntimeError("CHAT_ID is required")

try:
    TZ = pytz.timezone(TZ_NAME)
except Exception:
    TZ = pytz.timezone("America/Los_Angeles")

def now_local() -> datetime:
    return datetime.now(TZ)

# Вытаскиваем путь вебхука из WEBHOOK_URL; если нет — используем /hook-1111
if WEBHOOK_URL:
    HOOK_PATH = urlparse(WEBHOOK_URL).path or "/hook-1111"
else:
    HOOK_PATH = "/hook-1111"

PORT = int(os.getenv("PORT", "8080"))

# -------------------- ПАМЯТЬ ЛИДОВ --------------------
# Храним последние N лидов в памяти (без БД — достаточно для теста/продакшна на небольшой истории)
leads = deque(maxlen=1000)

LEAD_KEYWORDS = ("LEAD", "PROJECT REQUEST", "NEW PROJECT REQUEST")

def is_lead_text(text: str) -> bool:
    u = text.upper()
    return any(k in u for k in LEAD_KEYWORDS)

# -------------------- ХЕНДЛЕРЫ --------------------
async def ping(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not update.effective_chat or update.effective_chat.id != CHAT_ID:
        return
    await update.effective_message.reply_text("pong")

async def capture_leads(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Ловим все сообщения, логируем «сырые» тексты и складываем лиды в память."""
    if not update.effective_chat or update.effective_chat.id != CHAT_ID:
        return

    msg_text = ""
    if update.effective_message and update.effective_message.text:
        msg_text = update.effective_message.text.strip()
    elif update.effective_message and update.effective_message.caption:
        msg_text = update.effective_message.caption.strip()

    if msg_text:
        log.info("RAW TEXT: %r", msg_text)

        if is_lead_text(msg_text):
            leads.append((now_local(), msg_text))
            # Мягкое подтверждение, чтобы не спамить:
            try:
                await update.effective_message.reply_text("✅ Лид зафиксирован")
            except Exception as e:
                log.warning("Cannot reply confirm: %s", e)

async def summary(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not update.effective_chat or update.effective_chat.id != CHAT_ID:
        return

    ts = now_local().strftime("%Y-%m-%d %H:%M")
    if not leads:
        text = (
            f"📊 Summary {ts} — total: 0\n"
            f"• No matches.\n"
            f"Hey operators, any more leads? Please double-check!"
        )
    else:
        last_lines = [f"{dt.strftime('%m/%d %H:%M')} — {txt}" for dt, txt in list(leads)[-10:]]
        text = f"📊 Summary {ts} — total: {len(leads)}\n" + "\n".join(last_lines)

    await ctx.bot.send_message(chat_id=CHAT_ID, text=text)

# -------------------- MAIN --------------------
async def main() -> None:
    app: Application = (
        ApplicationBuilder()
        .token(BOT_TOKEN)
        .rate_limiter(AIORateLimiter())
        .build()
    )

    # Команды
    app.add_handler(CommandHandler("ping", ping))
    app.add_handler(CommandHandler("summary", summary))

    # Ловим все сообщения/посты и пытаемся выдернуть лиды
    app.add_handler(MessageHandler(filters.ALL, capture_leads))

    # Вебхук (оставляем как у тебя: Railway слушает порт, Telegram стучится по WEBHOOK_URL)
    log.info("Starting webhook server on port %s, path %s", PORT, HOOK_PATH)
    # Важно: вебхук в Телеге уже установлен вручную на WEBHOOK_URL (мы его НЕ сбрасываем здесь).
    # Если нужно — можно один раз выставить:
    # await app.bot.set_webhook(WEBHOOK_URL, drop_pending_updates=True)

    await app.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        url_path=HOOK_PATH,       # локальный путь сервера
        webhook_url=None,         # не трогаем уже выставленный в Telegram URL
        stop_signals=None,        # Railway сам убивает контейнер — не ждём сигналов
    )

if __name__ == "__main__":
    asyncio.run(main())
