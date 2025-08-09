import asyncio
import logging
import os
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

import aiosqlite
import pytz
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    AIORateLimiter,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

# ----------------------- Конфиг/переменные окружения -----------------------

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
CHAT_ID = int(os.getenv("CHAT_ID", "0"))
TZ_NAME = os.getenv("TIMEZONE", "America/Los_Angeles")
WEBHOOK_PUBLIC_URL = os.getenv("WEBHOOK_URL", "").strip()  # например https://.../hook-1111
PORT = int(os.getenv("PORT", "8080"))
LISTEN_ADDR = "0.0.0.0"

# окно отчёта (сегодня) и окно очистки (последние 3 часа)
CLEAN_WINDOW_HOURS = 3

# База
DB_PATH = os.getenv("DB_PATH", "leads.db")

# Пинги-шуточки для операторов (оставляю как у тебя было — несколько вариантов)
NUDGE_LINES = [
    "Hey operators, any more leads? Please double-check!",
    "Operators, are you alive or did the leads eat you? Share Volty’s conversion!",
    "Still on planet Earth, operators? Beam over Volty’s conversion numbers!",
    "Ping! Just checking if you exist. Also, where’s Volty’s conversion?",
]

# Включаем логирование покомфортнее
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
log = logging.getLogger("lead-counter-bot")

# Часовой пояс
try:
    TZ = pytz.timezone(TZ_NAME)
except Exception:
    TZ = pytz.utc

# ----------------------- Категории/распознавание -----------------------
# Имена в отчёте
DISPLAY = {
    "angi": "Angi leads",
    "yelp": "Yelp leads",
    "local": "Local",
    "website": "Website",
    "thumbtack": "Thumbtack leads",   # НОВОЕ
}

# Фиксированный порядок отображения
ORDER = ["angi", "yelp", "local", "website", "thumbtack"]


def classify_source(text: str) -> str | None:
    """
    Возвращает ключ категории (angi/yelp/local/website/thumbtack) или None.
    Распознавание максимально простое и устойчивое к регистру.
    """
    if not text:
        return None

    t = text.lower()

    # thumbtack (НОВОЕ)
    if "thumbtack" in t or "thumbtack.com" in t or "lead from thumbtack" in t:
        return "thumbtack"

    # angi
    if "angi" in t or "voltyx lead" in t or "angi.com" in t:
        return "angi"

    # yelp
    if "lead from yelp" in t or "yelp" in t:
        return "yelp"

    # local
    if "lead from local" in t:
        return "local"

    # website
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
    """
    Сохраняет лид. Возвращает True, если вставилось (новая запись),
    False — если уже есть такая связка chat_id+message_id.
    """
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


async def db_counts_for_today(tz: timezone) -> dict:
    """
    Считает количество лидов по категориям за сегодняшние сутки локального TZ.
    """
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
    """
    Удаляет записи за последние N часов. Возвращает число удалённых строк.
    """
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

    # формируем полный список категорий (даже если 0)
    lines = []
    total = 0
    for key in ORDER:
        c = counts.get(key, 0)
        total += c
        lines.append(f"• {DISPLAY[key]}: {c}")

    now_local = datetime.now(TZ)
    title = f"📊 Summary {now_local.strftime('%Y-%m-%d %H:%M')} — total: {total}"

    txt = title + "\n" + "\n".join(lines) + "\n" + f"\n{NUDGE_LINES[now_local.minute % len(NUDGE_LINES)]}"
    await update.effective_message.reply_text(txt)


async def cmd_clean(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Очищает лиды за последние 3 часа (CLEAN_WINDOW_HOURS).
    """
    if not update.effective_chat or update.effective_chat.id != CHAT_ID:
        return

    deleted = await db_clean_last_hours(CLEAN_WINDOW_HOURS)
    await update.effective_message.reply_text(
        f"🧹 Cleared {deleted} rows from the last {CLEAN_WINDOW_HOURS} hours."
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Отрабатывает любые новые сообщения в группе: пытаемся распознать лид, сохранить,
    и ответить ‘✅ Lead counted’.
    """
    msg = update.effective_message
    chat = update.effective_chat

    # только указанный чат
    if not chat or chat.id != CHAT_ID or not msg or not msg.text:
        return

    text = msg.text
    source = classify_source(text)
    if not source:
        # не похоже на лид — просто выходим
        return

    ts_utc = int(datetime.now(timezone.utc).timestamp())
    ok = await db_add_lead(chat.id, msg.message_id, ts_utc, source)
    if ok:
        try:
            await msg.reply_text("✅ Lead counted")
        except Exception:
            pass


# ----------------------- Webhook/приложение -----------------------

def parse_webhook_path(public_url: str) -> str:
    """
    Извлекаем path из PUBLIC_URL. Если пусто — дефолт /hook-1111.
    """
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

    # Команды
    application.add_handler(CommandHandler("ping", cmd_ping, filters=filters.Chat(CHAT_ID)))
    application.add_handler(CommandHandler("summary", cmd_summary, filters=filters.Chat(CHAT_ID)))
    application.add_handler(CommandHandler("clean", cmd_clean, filters=filters.Chat(CHAT_ID)))  # НОВОЕ

    # Сообщения в группе
    application.add_handler(MessageHandler(filters.Chat(CHAT_ID) & filters.TEXT, handle_message))

    return application


def main():
    app = build_application()

    # webhook
    path = parse_webhook_path(WEBHOOK_PUBLIC_URL)
    log.info(
        "Running webhook at %s:%s path=%s, public_url=%s",
        LISTEN_ADDR,
        PORT,
        path,
        WEBHOOK_PUBLIC_URL or "(NOT SET!)",
    )

    # run_webhook сам выставит setWebhook
    app.run_webhook(
        listen=LISTEN_ADDR,
        port=PORT,
        webhook_url=WEBHOOK_PUBLIC_URL if WEBHOOK_PUBLIC_URL else None,
        secret_token=None,
        allowed_updates=["message", "edited_message"],
        url_path=path,  # safe: PTB21 игнорит, когда указан webhook_url
    )


if __name__ == "__main__":
    main()
