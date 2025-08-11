import os
import logging
import random
import asyncio
import re
import unicodedata
from datetime import datetime, timedelta, timezone, time as dtime
from zoneinfo import ZoneInfo
from urllib.parse import urlparse

import aiosqlite
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

# ======================== ENV / CONFIG ========================
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
CHAT_ID = int(os.getenv("CHAT_ID", "0"))
TZ_NAME = os.getenv("TIMEZONE", "America/Los_Angeles").strip()
WEBHOOK_PUBLIC_URL = os.getenv("WEBHOOK_URL", "").strip()  # например: https://lead-counter-bot-production.up.railway.app/hook-1111
PORT = int(os.getenv("PORT", "8080"))
LISTEN_ADDR = "0.0.0.0"
DB_PATH = os.getenv("DB_PATH", "leads.db")
CLEAN_WINDOW_HOURS = 3

if not BOT_TOKEN or not CHAT_ID or not WEBHOOK_PUBLIC_URL:
    raise RuntimeError("Set BOT_TOKEN, CHAT_ID, WEBHOOK_URL environment variables")

LA = ZoneInfo(TZ_NAME)  # TZ для джобов/отчётов

# ======================== LOG ========================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
log = logging.getLogger("lead-counter-bot")

# ======================== ТЕКСТЫ НАПОМИНАНИЙ (10) ========================
REMINDERS = [
    "Хей, уважаемые операторы! Лид не пропустили? Всё ок? 😺",
    "Команда, just checking — всё ли в порядке с последним лидом? 😺",
    "Операторы, быстрый пинг: лид в работе, всё норм? 😺",
    "Эй, команда! Подтвердите, что лид под контролем, плиз. 😺",
    "Напоминалка: последний лид в порядке? Если что — маякните. 😺",
    "Привет! Уточняю: лид на месте, ничего не потерялось? 😺",
    "Friendly check: лид обработан? Дайте знать, если что-то нужно. 😺",
    "Йо-хо! Всё ли хорошо с лидом? Не пропустили? 😺",
    "Мини-пинг: лид виден/в работе? Спасибо! 😺",
    "Команда, всё ли гладко с новым лидом? Если что — мы рядом. 😺",
]

# ======================== КАТЕГОРИИ / РАСПОЗНАВАНИЕ ========================
DISPLAY = {
    "angi": "Angi leads",
    "yelp": "Yelp leads",
    "local": "Local",
    "website": "Website",
    "thumbtack": "Thumbtack leads",
}
ORDER = ["angi", "yelp", "local", "website", "thumbtack"]

def norm_text(text: str) -> str:
    """Нормализация: NFKC, убираем неразрывные пробелы, к нижнему регистру."""
    if not text:
        return ""
    t = unicodedata.normalize("NFKC", text)
    t = t.replace("\u00A0", " ")
    return t.casefold()

def classify_source(text: str) -> str | None:
    if not text:
        return None
    t = norm_text(text)

    # WEBSITE — ловим 'website', 'main page', допускаем варианты
    if ("website" in t) or ("main page" in t) or re.search(r"\bweb\s?site\b", t):
        return "website"

    # LOCAL — допускаем разные пробелы/эмодзи между словами
    if re.search(r"lead\s+from\s+local", t):
        return "local"
    if "local" in t and "lead" in t:
        return "local"

    # Yelp
    if re.search(r"lead\s+from\s+yelp", t) or "yelp" in t:
        return "yelp"

    # Angi
    if "angi" in t or "angi.com" in t or "voltyx lead" in t:
        return "angi"

    # Thumbtack (в т.ч. 'LEAD from Thumbtack')
    if "lead from thumbtack" in t or "thumbtack" in t or "thumbtack.com" in t:
        return "thumbtack"

    return None

# ======================== БД ========================
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

async def db_counts_between(start_local: datetime, end_local: datetime) -> dict[str, int]:
    start_utc = int(start_local.astimezone(timezone.utc).timestamp())
    end_utc = int(end_local.astimezone(timezone.utc).timestamp())
    sql = """
        SELECT source, COUNT(*)
        FROM leads
        WHERE ts_utc >= ? AND ts_utc < ?
        GROUP BY source
    """
    out: dict[str, int] = {}
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(sql, (start_utc, end_utc)) as cur:
            async for row in cur:
                out[row[0]] = row[1]
    return out

async def db_counts_today() -> dict[str, int]:
    now_l = datetime.now(LA)
    start = now_l.replace(hour=0, minute=0, second=0, microsecond=0)
    return await db_counts_between(start, now_l)

async def db_clean_last_hours(hours: int) -> int:
    now_utc = int(datetime.now(timezone.utc).timestamp())
    threshold = now_utc - hours * 3600
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("DELETE FROM leads WHERE ts_utc >= ?", (threshold,))
        await db.commit()
        return cur.rowcount

# ======================== ХЕЛПЕРЫ ОТЧЁТОВ ========================
def fmt_summary_lines(counts: dict[str, int]) -> tuple[str, int]:
    total = 0
    lines = []
    for key in ORDER:
        c = counts.get(key, 0)
        total += c
        lines.append(f"• {DISPLAY[key]}: {c}")
    return "\n".join(lines), total

async def send_summary_for_window(ctx: ContextTypes.DEFAULT_TYPE, start_local: datetime, end_local: datetime, title_prefix: str):
    counts = await db_counts_between(start_local, end_local)
    body, total = fmt_summary_lines(counts)
    title = f"{title_prefix} — total: {total}"
    await ctx.bot.send_message(CHAT_ID, f"{title}\n{body}")

# ======================== НАПОМИНАНИЕ (5 мин) ========================
async def delayed_reminder(ctx: ContextTypes.DEFAULT_TYPE):
    await asyncio.sleep(300)  # 5 минут
    try:
        await ctx.bot.send_message(chat_id=CHAT_ID, text=random.choice(REMINDERS))
    except Exception:
        pass

# ======================== ХЕНДЛЕРЫ ========================
async def cmd_ping(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat and update.effective_chat.id == CHAT_ID:
        await update.effective_message.reply_text("pong")

async def cmd_summary(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_chat or update.effective_chat.id != CHAT_ID:
        return
    counts = await db_counts_today()
    body, total = fmt_summary_lines(counts)
    now_local = datetime.now(LA).strftime('%Y-%m-%d %H:%M')
    await update.effective_message.reply_text(f"📊 Summary {now_local} — total: {total}\n{body}")

async def cmd_clean(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_chat or update.effective_chat.id != CHAT_ID:
        return
    deleted = await db_clean_last_hours(CLEAN_WINDOW_HOURS)
    await update.effective_message.reply_text(f"🧹 Cleared {deleted} rows from the last {CLEAN_WINDOW_HOURS} hours.")

# /undo и "/-" — удалить последний лид
async def cmd_remove_last(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_chat or update.effective_chat.id != CHAT_ID:
        return
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT id, source, ts_utc FROM leads ORDER BY ts_utc DESC LIMIT 1")
        row = await cur.fetchone()
        if not row:
            await update.effective_message.reply_text("❌ Нет лидов для удаления.")
            return
        lead_id, source, ts_utc = row
        await db.execute("DELETE FROM leads WHERE id = ?", (lead_id,))
        await db.commit()
    ts_local = datetime.fromtimestamp(ts_utc, LA).strftime('%Y-%m-%d %H:%M')
    await update.effective_message.reply_text(f"➖ Удалён последний лид ({DISPLAY.get(source, source)} @ {ts_local})")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    chat = update.effective_chat
    if not chat or chat.id != CHAT_ID or not msg:
        return

    # Учитываем и текст, и подписи к медиа
    content = (msg.text or msg.caption or "").strip()
    if not content:
        return

    source = classify_source(content)
    if not source:
        return

    ts_utc = int(datetime.now(timezone.utc).timestamp())
    inserted = await db_add_lead(chat.id, msg.message_id, ts_utc, source)
    if inserted:
        try:
            await msg.reply_text("✅ Lead counted")
        except Exception:
            pass
        try:
            context.application.create_task(delayed_reminder(context))
        except Exception:
            pass

# ======================== АВТО‑ОТЧЁТЫ (08:00 / 16:00 / 20:00) ========================
async def job_08(context: ContextTypes.DEFAULT_TYPE):
    # 08:00 — ночь: вчера 20:00 → сегодня 08:00
    now_l = datetime.now(LA)
    start = (now_l - timedelta(days=1)).replace(hour=20, minute=0, second=0, microsecond=0)
    end   = now_l.replace(hour=8, minute=0, second=0, microsecond=0)
    await send_summary_for_window(context, start, end, f"🌙 Night summary {start.strftime('%Y-%m-%d 20:00')} → {end.strftime('%Y-%m-%d 08:00')}")

async def job_16(context: ContextTypes.DEFAULT_TYPE):
    # 16:00 — утро: сегодня 08:00 → 16:00
    now_l = datetime.now(LA)
    start = now_l.replace(hour=8, minute=0, second=0, microsecond=0)
    end   = now_l.replace(hour=16, minute=0, second=0, microsecond=0)
    await send_summary_for_window(context, start, end, f"🌤️ Day summary {start.strftime('%Y-%m-%d 08:00')} → {end.strftime('%Y-%m-%d 16:00')}")

async def job_20(context: ContextTypes.DEFAULT_TYPE):
    # 20:00 — вечер: сегодня 16:00 → 20:00
    now_l = datetime.now(LA)
    start = now_l.replace(hour=16, minute=0, second=0, microsecond=0)
    end   = now_l.replace(hour=20, minute=0, second=0, microsecond=0)
    await send_summary_for_window(context, start, end, f"🌆 Evening summary {start.strftime('%Y-%m-%d 16:00')} → {end.strftime('%Y-%m-%d 20:00')}")

# ======================== СБОРКА / ЗАПУСК ========================
async def on_startup(app: Application):
    await db_init()

def build_application() -> Application:
    app = (
        ApplicationBuilder()
        .token(BOT_TOKEN)
        .post_init(on_startup)
        .build()
    )

    # Команды
    app.add_handler(CommandHandler("ping",    cmd_ping,    filters=filters.Chat(CHAT_ID)))
    app.add_handler(CommandHandler("summary", cmd_summary, filters=filters.Chat(CHAT_ID)))
    app.add_handler(CommandHandler("clean",   cmd_clean,   filters=filters.Chat(CHAT_ID)))
    app.add_handler(CommandHandler("undo",    cmd_remove_last, filters=filters.Chat(CHAT_ID)))  # официальная команда

    # Дополнительно ловим именно строку "/-" (через Regex)
    app.add_handler(MessageHandler(filters.Chat(CHAT_ID) & filters.Regex(r"^/\-$"), cmd_remove_last))

    # Сообщения с лидами: TEXT и CAPTION
    app.add_handler(MessageHandler(filters.Chat(CHAT_ID) & (filters.TEXT | filters.CAPTION), handle_message))

    # Планировщик авто‑сводок (тайзона задаётся прямо в time)
    jq = app.job_queue
    jq.run_daily(job_08, time=dtime(8, 0, tzinfo=LA))
    jq.run_daily(job_16, time=dtime(16, 0, tzinfo=LA))
    jq.run_daily(job_20, time=dtime(20, 0, tzinfo=LA))

    return app

def parse_webhook_path(public_url: str) -> str:
    if not public_url:
        return "/hook-1111"
    try:
        p = urlparse(public_url)
        return p.path if p.path else "/hook-1111"
    except Exception:
        return "/hook-1111"

def main():
    app = build_application()
    path = parse_webhook_path(WEBHOOK_PUBLIC_URL)
    logging.getLogger().info(
        "Running webhook at %s:%s path=%s url=%s",
        LISTEN_ADDR, PORT, path, WEBHOOK_PUBLIC_URL or "(NOT SET!)"
    )
    app.run_webhook(
        listen=LISTEN_ADDR,
        port=PORT,
        webhook_url=WEBHOOK_PUBLIC_URL,
        allowed_updates=["message", "edited_message"],
        url_path=path,
    )

if __name__ == "__main__":
    main()
