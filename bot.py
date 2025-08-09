import logging
import os
import random
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

import aiosqlite
import pytz
from telegram import Update
from telegram.ext import (
    Application,
    AIORateLimiter,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

# ----------------------- Конфиг / env -----------------------

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
CHAT_ID = int(os.getenv("CHAT_ID", "0"))
TZ_NAME = os.getenv("TIMEZONE", "America/Los_Angeles")
WEBHOOK_PUBLIC_URL = os.getenv("WEBHOOK_URL", "").strip()  # https://.../hook-1111
PORT = int(os.getenv("PORT", "8080"))
LISTEN_ADDR = "0.0.0.0"

# Сколько часов чистим по /clean
CLEAN_WINDOW_HOURS = 3

# Файл БД
DB_PATH = os.getenv("DB_PATH", "leads.db")

# Полные подталкивающие фразы (10 шт.) — каждая пойдёт и после /summary, и после каждого лида
NUDGE_LINES = [
    "Dear Operators, if you read this, send Volty’s conversion… or we’ll assume you’ve joined the witness protection program!",
    "Hey operators! Are you alive? Please share Volty’s conversion numbers.",
    "Operators, don’t be shy—drop Volty’s conversion in the chat!",
    "Ping! If you can see this, send Volty’s conversion. Pretty please.",
    "Still breathing, team? Post Volty’s conversion before the coffee gets cold.",
    "Friendly poke: conversion, please. Volty is watching. 👀",
    "Quick check-in: any updates on conversion? Don’t ghost us!",
    "Hello, humans! Kindly provide Volty’s conversion before we send a search party.",
    "Conversion status, anyone? We promise not to judge… much.",
    "If you can read this, it’s a sign to send the conversion. Now. Thank you!",
]

# Логирование
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
log = logging.getLogger("lead-counter-bot")

# TZ
try:
    TZ = pytz.timezone(TZ_NAME)
except Exception:
    TZ = pytz.utc

# ----------------------- Категории / распознавание -----------------------

DISPLAY = {
    "angi": "Angi leads",
    "yelp": "Yelp leads",
    "local": "Local",
    "website": "Website",
    "thumbtack": "Thumbtack leads",   # НОВОЕ
}

ORDER = ["angi", "yelp", "local", "website", "thumbtack"]


def classify_source(text: str) -> str | None:
    if not text:
        return None
    t = text.lower()

    # Thumbtack
    if "thumbtack" in t or "thumbtack.com" in t or "lead from thumbtack" in t:
        return "thumbtack"

    # Angi
    if "angi" in t or "voltyx lead" in t or "angi.com" in t:
        return "angi"

    # Yelp
    if "lead from yelp" in t or "yelp" in t:
        return "yelp"

    # Local
    if "lead from local" in t:
        return "local"

    # Website
    if "website" in t or "check website" in t:
        return "website"

    return None


# ----------------------- БД -----------------------

INIT_SQL = """
CREATE TABLE IF NOT EXISTS leads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id INTEGER NOT NULL,
    message_id INTEGER NOT NULL,
    ts_utc INTEGER NOT NULL,
    source TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_unique_msg ON leads(chat_id, message_id);
CREATE INDEX IF NOT EXISTS idx_ts ON leads(ts_utc);
CREATE INDEX IF NOT EXISTS idx_source ON leads(source);
"""


async def db_init():
    async with aiosqlite.connect(DB_PATH) as db:
        for stmt in INIT_SQL.strip().split(";"):
            s = stmt.strip()
            if s:
                await db.execute(s)
        await db.commit()


async def db_add_lead(chat_id: int, message_id: int, ts_utc: int, source: str) -> bool:
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "INSERT INTO leads(chat_id, message_id, ts_utc, source) VALUES (?, ?, ?, ?)",
                (chat_id, message_id, ts_utc, source),
            )
            await db.commit()
        return True
    except aiosqlite.IntegrityError:
        return False


async def db_counts_for_today(tz) -> dict:
    now_local = datetime.now(tz)
    start_local = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
    start_utc = int(start_local.astimezone(timezone.utc).timestamp())
    end_utc = int(now_local.astimezone(timezone.utc).timestamp())

    sql = """
        SELECT source, COUNT(*)
        FROM leads
        WHERE ts_utc BETWEEN ? AND ?
        GROUP BY source
    """
    out: dict = {}
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(sql, (start_utc, end_utc)) as cur:
            async for row in cur:
                out[row[0]] = row[1]
    return out


async def db_clean_last_hours(hours: int) -> int:
    now_utc = int(datetime.now(timezone.utc).timestamp())
    threshold = now_utc - hours * 3600
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("DELETE FROM leads WHERE ts_utc >= ?", (threshold,))
        await db.commit()
        return cur.rowcount


# ----------------------- Хэндлеры -----------------------

async def cmd_ping(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat and update.effective_chat.id == CHAT_ID:
        await update.effective_message.reply_text("pong")


async def cmd_summary(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_chat or update.effective_chat.id != CHAT_ID:
        return

    counts = await db_counts_for_today(TZ)

    total = 0
    lines = []
    for key in ORDER:
        c = counts.get(key, 0)
        total += c
        lines.append(f"• {DISPLAY[key]}: {c}")

    now_local = datetime.now(TZ)
    title = f"📊 Summary {now_local.strftime('%Y-%m-%d %H:%M')} — total: {total}"

    tail = random.choice(NUDGE_LINES)
    txt = title + "\n" + "\n".join(lines) + "\n\n" + tail
    await update.effective_message.reply_text(txt)


async def cmd_clean(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_chat or update.effective_chat.id != CHAT_ID:
        return
    deleted = await db_clean_last_hours(CLEAN_WINDOW_HOURS)
    await update.effective_message.reply_text(
        f"🧹 Cleared {deleted} rows from the last {CLEAN_WINDOW_HOURS} hours."
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    chat = update.effective_chat
    if not chat or chat.id != CHAT_ID or not msg or not msg.text:
        return

    source = classify_source(msg.text)
    if not source:
        return

    ts_utc = int(datetime.now(timezone.utc).timestamp())
    inserted = await db_add_lead(chat.id, msg.message_id, ts_utc, source)
    if inserted:
        # 1) подтверждение
        try:
            await msg.reply_text("✅ Lead counted")
        except Exception:
            pass
        # 2) следом — одна из 10 английских подсказок операторам
        try:
            await context.bot.send_message(chat_id=CHAT_ID, text=random.choice(NUDGE_LINES))
        except Exception:
            pass


# ----------------------- Webhook / приложение -----------------------

def parse_webhook_path(public_url: str) -> str:
    if not public_url:
        return "/hook-1111"
    try:
        p = urlparse(public_url)
        return p.path if p.path else "/hook-1111"
    except Exception:
        return "/hook-1111"


async def on_startup(app: Application):
    await db_init()


def build_application() -> Application:
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN is not set")

    application = (
        Application.builder()
        .token(BOT_TOKEN)
        .rate_limiter(AIORateLimiter())
        .post_init(on_startup)
        .build()
    )

    application.add_handler(CommandHandler("ping", cmd_ping, filters=filters.Chat(CHAT_ID)))
    application.add_handler(CommandHandler("summary", cmd_summary, filters=filters.Chat(CHAT_ID)))
    application.add_handler(CommandHandler("clean", cmd_clean, filters=filters.Chat(CHAT_ID)))

    application.add_handler(MessageHandler(filters.Chat(CHAT_ID) & filters.TEXT, handle_message))

    return application


def main():
    app = build_application()
    path = parse_webhook_path(WEBHOOK_PUBLIC_URL)

    logging.getLogger().info(
        "Running webhook at %s:%s path=%s, public_url=%s",
        LISTEN_ADDR, PORT, path, WEBHOOK_PUBLIC_URL or "(NOT SET!)"
    )

    app.run_webhook(
        listen=LISTEN_ADDR,
        port=PORT,
        webhook_url=WEBHOOK_PUBLIC_URL if WEBHOOK_PUBLIC_URL else None,
        allowed_updates=["message", "edited_message"],
        url_path=path,
    )


if __name__ == "__main__":
    main()
