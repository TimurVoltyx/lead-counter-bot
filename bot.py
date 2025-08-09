# bot.py
# =======
# Требуются env-переменные: BOT_TOKEN, CHAT_ID, TIMEZONE, WEBHOOK_URL
# requirements.txt: python-telegram-bot[rate-limiter,job-queue,webhooks]==21.4, aiosqlite, pytz

import os
import logging
from urllib.parse import urlparse
from datetime import datetime, timedelta, timezone

from telegram import Update
from telegram.ext import (
    Application, ApplicationBuilder,
    CommandHandler, MessageHandler, ContextTypes, filters
)

# ---------- ЛОГИ ----------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s"
)
log = logging.getLogger("lead-counter-bot")

# ---------- ENV ----------
BOT_TOKEN   = os.getenv("BOT_TOKEN", "").strip()
CHAT_ID_RAW = os.getenv("CHAT_ID", "").strip()
TIMEZONE    = os.getenv("TIMEZONE", "America/Los_Angeles").strip()
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "").strip()  # например: https://lead-counter-bot-production.up.railway.app/hook-1111

if not BOT_TOKEN:
    raise RuntimeError("ENV BOT_TOKEN is empty")
if not CHAT_ID_RAW:
    raise RuntimeError("ENV CHAT_ID is empty")
try:
    CHAT_ID = int(CHAT_ID_RAW)  # для супергрупп будет отрицательный
except ValueError:
    raise RuntimeError("ENV CHAT_ID must be integer (e.g. -1002485440713)")

if not WEBHOOK_URL:
    raise RuntimeError("ENV WEBHOOK_URL is empty (like https://.../hook-1111)")

# ---------- ВРЕМЕННАЯ ЗОНА ----------
try:
    import zoneinfo
    TZ = zoneinfo.ZoneInfo(TIMEZONE)
except Exception:
    TZ = timezone.utc
    log.warning("Could not load timezone '%s', fallback to UTC", TIMEZONE)

# ---------- ВСПОМОГАТЕЛЬНОЕ ----------
def now_local():
    return datetime.now(TZ)

# Простая заглушка для /summary — вернёт 0 и пинганёт операторов
async def cmd_summary(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    # фильтруем по нашему чату
    if update.effective_chat and update.effective_chat.id != CHAT_ID:
        return

    ts = now_local().strftime("%Y-%m-%d %H:%M")
    text = (
        f"📊 Summary {ts} — total: 0\n"
        f"• No matches.\n"
        f"Hey operators, any more leads? Please double-check!"
    )
    await ctx.bot.send_message(chat_id=CHAT_ID, text=text)

# Простой ping
async def cmd_ping(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat and update.effective_chat.id != CHAT_ID:
        return
    await ctx.bot.send_message(chat_id=CHAT_ID, text="pong")

# ---------- ГЛАВНЫЙ ОТЛАДОЧНЫЙ ОБРАБОТЧИК ----------
# Ловит ВСЕ апдейты из нашего чата. Если бот ничего не отвечает — апдейты не доходят.
async def debug_all(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    # ограничиваем только нашим чатом, чтобы не шуметь
    if update.effective_chat and update.effective_chat.id != CHAT_ID:
        return

    try:
        payload = update.to_dict()
        log.info("RAW UPDATE: %s", payload)
    except Exception as e:
        log.exception("Failed to dump update: %s", e)

    # Покажем, что бот реально видит сообщение
    try:
        if update.effective_message:
            await update.effective_message.reply_text("Лщвите его!")
        else:
            # если нет message (например callback_query и т.п.), шлем отдельным send_message
            await ctx.bot.send_message(chat_id=CHAT_ID, text="Я вижу апдейт (не message)!")
    except Exception as e:
        log.exception("Failed to reply in debug_all: %s", e)

# ---------- MAIN ----------
def main():
    log.info("Starting bot, CHAT_ID=%s, TZ=%s", CHAT_ID, TIMEZONE)

    app: Application = ApplicationBuilder().token(BOT_TOKEN).build()

    # Команды
    app.add_handler(CommandHandler("summary", cmd_summary))
    app.add_handler(CommandHandler("ping", cmd_ping))

    # ОТЛАДОЧНЫЙ ХЕНДЛЕР — ВСЁ, ЧТО ПРИХОДИТ
    app.add_handler(MessageHandler(filters.ALL, debug_all))

    # ---- WEBHOOK ----
    # Railway слушает порт 8080. path берём из WEBHOOK_URL (/hook-xxxx)
    parsed = urlparse(WEBHOOK_URL)
    hook_path = parsed.path if parsed.path else "/hook"
    # Важное: set_webhook делает сама PTB внутри run_webhook
    log.info("Running webhook at 0.0.0.0:8080 path=%s, public_url=%s", hook_path, WEBHOOK_URL)

    app.run_webhook(
        listen="0.0.0.0",
        port=8080,
        url_path=hook_path.lstrip("/"),
        webhook_url=WEBHOOK_URL
    )

if __name__ == "__main__":
    main()
