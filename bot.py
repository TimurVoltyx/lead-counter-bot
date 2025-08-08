# lead-counter-bot: 08–16, 16–20, 20–08 + /summary + шутки (PTB 21.x)
import asyncio, os, re, random, aiosqlite, pytz
from datetime import datetime, time, timedelta
from telegram import Update
from telegram.ext import (
    Application, MessageHandler, CommandHandler,
    ContextTypes, AIORateLimiter, filters,
)

# ------- ОКРУЖЕНИЕ -------
TOKEN   = os.getenv("BOT_TOKEN")                      # токен без @
CHAT_ID = int(os.getenv("CHAT_ID", "0"))              # например: -1002485440713
TZ      = pytz.timezone(os.getenv("TIMEZONE", "America/Los_Angeles"))
DB = "counts.sqlite3"

# ------- РАСПОЗНАВАНИЕ ИСТОЧНИКОВ -------
CATS = {
    "Angi leads": [r"\bangi\b", r"\bangi\s+leads?\b"],
    "Yelp leads": [r"\byelp\b", r"\byelp\s+leads?\b"],
    "Website":    [r"\bwebsite\b", r"\b(site|web)\s?form\b"],
    "Local":      [r"\blocal\b", r"\bgoogle\s?(ads|maps)?\b"],
}

# ------- ШУТОЧНЫЕ ПИНКИ -------
JOKES = [
    "Hey operators! Still breathing out there? Drop Volty’s conversion, please!",
    "Operators, are you alive or did the leads eat you? Share Volty’s conversion!",
    "Yo team! Blink twice if you’re alive… and send Volty’s conversion rate!",
    "Operators, quit hiding! We need Volty’s conversion stats before they fossilize!",
    "Knock knock… anyone home? Time to spill Volty’s conversion beans!",
    "Dear Operators, if you read this, send Volty’s conversion… or we’ll assume you’ve joined the witness protection program!",
    "Still on planet Earth, operators? Beam over Volty’s conversion numbers!",
    "Ping! Just checking if you exist. Also, where’s Volty’s conversion?",
    "Operators, is it nap time? Wake up and give us Volty’s conversion, pronto!",
    "Hello from the outside 🎶… now send Volty’s conversion from the inside!",
]

# ------- ВСПОМОГАТЕЛЬНОЕ -------
def now() -> datetime:
    return datetime.now(TZ)

def window_name(dt: datetime) -> str:
    t = dt.time()
    if time(8,0)  <= t < time(16,0): return "08-16"
    if time(16,0) <= t < time(20,0): return "16-20"
    return "20-08"

def window_key_date(dt: datetime) -> str:
    """Дата начала окна (ночь 00:00–07:59 относится к вчерашнему 20:00)."""
    w = window_name(dt)
    d = dt.date()
    if w == "20-08" and dt.time() < time(8,0):
        d = d - timedelta(days=1)
    return d.strftime("%Y-%m-%d")

async def init_db():
    async with aiosqlite.connect(DB) as db:
        await db.execute("""
        CREATE TABLE IF NOT EXISTS counts(
            chat_id INTEGER,
            date TEXT,       -- дата начала окна
            window TEXT,     -- 08-16 | 16-20 | 20-08
            category TEXT,
            cnt INTEGER,
            PRIMARY KEY(chat_id, date, window, category)
        )""")
        await db.commit()

def classify(text: str) -> str | None:
    t = (text or "").lower()
    for name, pats in CATS.items():
        for p in pats:
            if re.search(p, t):
                return name
    return None

async def bump(cat: str, dt: datetime):
    d = window_key_date(dt)
    w = window_name(dt)
    async with aiosqlite.connect(DB) as db:
        await db.execute("""
            INSERT INTO counts(chat_id, date, window, category, cnt)
            VALUES(?, ?, ?, ?, 1)
            ON CONFLICT(chat_id, date, window, category)
            DO UPDATE SET cnt = cnt + 1
        """, (CHAT_ID, d, w, cat))
        await db.commit()

# ------- СБОР СООБЩЕНИЙ -------
async def on_any(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    # считаем только в целевом чате
    if not update.effective_chat or int(update.effective_chat.id) != CHAT_ID:
        return

    text = ""
    if update.effective_message:
        text = (update.effective_message.text or update.effective_message.caption or "")
    elif update.channel_post:
        text = (update.channel_post.text or update.channel_post.caption or "")

    cat = classify(text)
    if cat:
        await bump(cat, now())

# ------- СВОДКИ -------
async def summary_for(window: str, date_key: str) -> str:
    async with aiosqlite.connect(DB) as db:
        cur = await db.execute("""
            SELECT category, cnt FROM counts
            WHERE chat_id=? AND date=? AND window=?
            ORDER BY cnt DESC
        """, (CHAT_ID, date_key, window))
        rows = await cur.fetchall()

    total = sum(c for _, c in rows)
    lines = [f"📊 Summary {date_key} {window} — total: {total}"]
    lines += [f"• {cat}: {cnt}" for cat, cnt in rows] or ["• No matches."]
    lines.append("Hey operators, any more leads? Please double-check!")
    return "\n".join(lines)

async def send_joke(ctx: ContextTypes.DEFAULT_TYPE):
    await ctx.bot.send_message(CHAT_ID, random.choice(JOKES))

# расписание
async def send_16(ctx: ContextTypes.DEFAULT_TYPE):
    date_key = now().date().strftime("%Y-%m-%d")
    await ctx.bot.send_message(CHAT_ID, await summary_for("08-16", date_key))
    await send_joke(ctx)

async def send_20(ctx: ContextTypes.DEFAULT_TYPE):
    date_key = now().date().strftime("%Y-%m-%d")
    await ctx.bot.send_message(CHAT_ID, await summary_for("16-20", date_key))
    await send_joke(ctx)

async def send_08(ctx: ContextTypes.DEFAULT_TYPE):
    date_key = (now().date() - timedelta(days=1)).strftime("%Y-%m-%d")
    await ctx.bot.send_message(CHAT_ID, await summary_for("20-08", date_key))
    await send_joke(ctx)

# ручная команда (последнее оконченное окно по умолчанию)
def last_window_and_date(dt: datetime) -> tuple[str, str]:
    t = dt.time()
    if t < time(8,0):           # 00:00–07:59 → последняя ночь (вчера)
        return "20-08", (dt.date() - timedelta(days=1)).strftime("%Y-%m-%d")
    if t < time(16,0):          # 08:00–15:59
        return "08-16", dt.date().strftime("%Y-%m-%d")
    if t < time(20,0):          # 16:00–19:59
        return "16-20", dt.date().strftime("%Y-%m-%d")
    return "20-08", dt.date().strftime("%Y-%m-%d")  # 20:00–23:59

async def _do_summary(window_arg: str | None, ctx: ContextTypes.DEFAULT_TYPE):
    now_dt = now()
    if window_arg in ("08-16", "16-20", "20-08", "night"):
        window = "20-08" if window_arg == "night" else window_arg
        date_key = (now_dt.date() - timedelta(days=1)).strftime("%Y-%m-%d") if window == "20-08" else now_dt.date().strftime("%Y-%m-%d")
    else:
        window, date_key = last_window_and_date(now_dt)

    await ctx.bot.send_message(CHAT_ID, await summary_for(window, date_key))
    await send_joke(ctx)

# стандартная команда /summary (в начале сообщения)
async def cmd_summary(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if int(update.effective_chat.id) != CHAT_ID:
        return
    arg = (ctx.args[0].lower() if ctx.args else "").strip()
    await _do_summary(arg or None, ctx)

# Фолбек: ловим сообщения, где /summary стоит не в начале (например "@bot /summary" или текст + /summary)
async def fallback_summary_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if int(update.effective_chat.id) != CHAT_ID:
        return
    text = (update.effective_message and update.effective_message.text) or ""
    low = text.lower()

    if "/summary" in low:
        # попытаемся выцепить аргумент (например "/summary 16-20")
        arg = None
        parts = low.split()
        for i, p in enumerate(parts):
            if p.startswith("/summary"):
                if i + 1 < len(parts):
                    cand = parts[i + 1].strip()
                    if cand in ("08-16", "16-20", "20-08", "night"):
                        arg = cand
                break
        await _do_summary(arg, ctx)

# ------- СТАРТ -------
async def main():
    if not TOKEN or CHAT_ID == 0:
        raise RuntimeError("BOT_TOKEN/CHAT_ID/TIMEZONE not set in Railway Variables.")

    await init_db()

    app = (Application.builder()
           .token(TOKEN)
           .rate_limiter(AIORateLimiter())
           .build())

    # собираем лиды
    app.add_handler(MessageHandler(filters.Chat(CHAT_ID) & (filters.TEXT | filters.CAPTION), on_any))
    app.add_handler(MessageHandler(filters.ChatType.CHANNEL & (filters.TEXT | filters.CAPTION), on_any))

    # команды: обычная команда + фолбек-текст
    app.add_handler(CommandHandler("summary", cmd_summary))            # без фильтра, но внутри проверяем CHAT_ID
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, fallback_summary_text))

    # расписание через tzinfo
    app.job_queue.run_daily(send_16, time(16, 0, tzinfo=TZ))
    app.job_queue.run_daily(send_20, time(20, 0, tzinfo=TZ))
    app.job_queue.run_daily(send_08, time(8,  0, tzinfo=TZ))

    # корректный цикл (без run_polling() внутри asyncio.run)
    await app.initialize()
    await app.start()
    try:
        await app.updater.start_polling(allowed_updates=Update.ALL_TYPES)
        await asyncio.Event().wait()
    finally:
        await app.updater.stop()
        await app.stop()
        await app.shutdown()

if __name__ == "__main__":
    asyncio.run(main())
# lead-counter-bot: 08–16, 16–20, 20–08 + /summary + шутки (PTB 21.x)
import asyncio, os, re, random, aiosqlite, pytz
from datetime import datetime, time, timedelta
from telegram import Update
from telegram.ext import (
    Application, MessageHandler, CommandHandler,
    ContextTypes, AIORateLimiter, filters,
)

# ------- ОКРУЖЕНИЕ -------
TOKEN   = os.getenv("BOT_TOKEN")                      # токен без @
CHAT_ID = int(os.getenv("CHAT_ID", "0"))              # например: -1002485440713
TZ      = pytz.timezone(os.getenv("TIMEZONE", "America/Los_Angeles"))
DB = "counts.sqlite3"

# ------- РАСПОЗНАВАНИЕ ИСТОЧНИКОВ -------
CATS = {
    "Angi leads": [r"\bangi\b", r"\bangi\s+leads?\b"],
    "Yelp leads": [r"\byelp\b", r"\byelp\s+leads?\b"],
    "Website":    [r"\bwebsite\b", r"\b(site|web)\s?form\b"],
    "Local":      [r"\blocal\b", r"\bgoogle\s?(ads|maps)?\b"],
}

# ------- ШУТОЧНЫЕ ПИНКИ -------
JOKES = [
    "Hey operators! Still breathing out there? Drop Volty’s conversion, please!",
    "Operators, are you alive or did the leads eat you? Share Volty’s conversion!",
    "Yo team! Blink twice if you’re alive… and send Volty’s conversion rate!",
    "Operators, quit hiding! We need Volty’s conversion stats before they fossilize!",
    "Knock knock… anyone home? Time to spill Volty’s conversion beans!",
    "Dear Operators, if you read this, send Volty’s conversion… or we’ll assume you’ve joined the witness protection program!",
    "Still on planet Earth, operators? Beam over Volty’s conversion numbers!",
    "Ping! Just checking if you exist. Also, where’s Volty’s conversion?",
    "Operators, is it nap time? Wake up and give us Volty’s conversion, pronto!",
    "Hello from the outside 🎶… now send Volty’s conversion from the inside!",
]

# ------- ВСПОМОГАТЕЛЬНОЕ -------
def now() -> datetime:
    return datetime.now(TZ)

def window_name(dt: datetime) -> str:
    t = dt.time()
    if time(8,0)  <= t < time(16,0): return "08-16"
    if time(16,0) <= t < time(20,0): return "16-20"
    return "20-08"

def window_key_date(dt: datetime) -> str:
    """Дата начала окна (ночь 00:00–07:59 относится к вчерашнему 20:00)."""
    w = window_name(dt)
    d = dt.date()
    if w == "20-08" and dt.time() < time(8,0):
        d = d - timedelta(days=1)
    return d.strftime("%Y-%m-%d")

async def init_db():
    async with aiosqlite.connect(DB) as db:
        await db.execute("""
        CREATE TABLE IF NOT EXISTS counts(
            chat_id INTEGER,
            date TEXT,       -- дата начала окна
            window TEXT,     -- 08-16 | 16-20 | 20-08
            category TEXT,
            cnt INTEGER,
            PRIMARY KEY(chat_id, date, window, category)
        )""")
        await db.commit()

def classify(text: str) -> str | None:
    t = (text or "").lower()
    for name, pats in CATS.items():
        for p in pats:
            if re.search(p, t):
                return name
    return None

async def bump(cat: str, dt: datetime):
    d = window_key_date(dt)
    w = window_name(dt)
    async with aiosqlite.connect(DB) as db:
        await db.execute("""
            INSERT INTO counts(chat_id, date, window, category, cnt)
            VALUES(?, ?, ?, ?, 1)
            ON CONFLICT(chat_id, date, window, category)
            DO UPDATE SET cnt = cnt + 1
        """, (CHAT_ID, d, w, cat))
        await db.commit()

# ------- СБОР СООБЩЕНИЙ -------
async def on_any(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    # считаем только в целевом чате
    if not update.effective_chat or int(update.effective_chat.id) != CHAT_ID:
        return

    text = ""
    if update.effective_message:
        text = (update.effective_message.text or update.effective_message.caption or "")
    elif update.channel_post:
        text = (update.channel_post.text or update.channel_post.caption or "")

    cat = classify(text)
    if cat:
        await bump(cat, now())

# ------- СВОДКИ -------
async def summary_for(window: str, date_key: str) -> str:
    async with aiosqlite.connect(DB) as db:
        cur = await db.execute("""
            SELECT category, cnt FROM counts
            WHERE chat_id=? AND date=? AND window=?
            ORDER BY cnt DESC
        """, (CHAT_ID, date_key, window))
        rows = await cur.fetchall()

    total = sum(c for _, c in rows)
    lines = [f"📊 Summary {date_key} {window} — total: {total}"]
    lines += [f"• {cat}: {cnt}" for cat, cnt in rows] or ["• No matches."]
    lines.append("Hey operators, any more leads? Please double-check!")
    return "\n".join(lines)

async def send_joke(ctx: ContextTypes.DEFAULT_TYPE):
    await ctx.bot.send_message(CHAT_ID, random.choice(JOKES))

# расписание
async def send_16(ctx: ContextTypes.DEFAULT_TYPE):
    date_key = now().date().strftime("%Y-%m-%d")
    await ctx.bot.send_message(CHAT_ID, await summary_for("08-16", date_key))
    await send_joke(ctx)

async def send_20(ctx: ContextTypes.DEFAULT_TYPE):
    date_key = now().date().strftime("%Y-%m-%d")
    await ctx.bot.send_message(CHAT_ID, await summary_for("16-20", date_key))
    await send_joke(ctx)

async def send_08(ctx: ContextTypes.DEFAULT_TYPE):
    date_key = (now().date() - timedelta(days=1)).strftime("%Y-%m-%d")
    await ctx.bot.send_message(CHAT_ID, await summary_for("20-08", date_key))
    await send_joke(ctx)

# ручная команда (последнее оконченное окно по умолчанию)
def last_window_and_date(dt: datetime) -> tuple[str, str]:
    t = dt.time()
    if t < time(8,0):           # 00:00–07:59 → последняя ночь (вчера)
        return "20-08", (dt.date() - timedelta(days=1)).strftime("%Y-%m-%d")
    if t < time(16,0):          # 08:00–15:59
        return "08-16", dt.date().strftime("%Y-%m-%d")
    if t < time(20,0):          # 16:00–19:59
        return "16-20", dt.date().strftime("%Y-%m-%d")
    return "20-08", dt.date().strftime("%Y-%m-%d")  # 20:00–23:59

async def _do_summary(window_arg: str | None, ctx: ContextTypes.DEFAULT_TYPE):
    now_dt = now()
    if window_arg in ("08-16", "16-20", "20-08", "night"):
        window = "20-08" if window_arg == "night" else window_arg
        date_key = (now_dt.date() - timedelta(days=1)).strftime("%Y-%m-%d") if window == "20-08" else now_dt.date().strftime("%Y-%m-%d")
    else:
        window, date_key = last_window_and_date(now_dt)

    await ctx.bot.send_message(CHAT_ID, await summary_for(window, date_key))
    await send_joke(ctx)

# стандартная команда /summary (в начале сообщения)
async def cmd_summary(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if int(update.effective_chat.id) != CHAT_ID:
        return
    arg = (ctx.args[0].lower() if ctx.args else "").strip()
    await _do_summary(arg or None, ctx)

# Фолбек: ловим сообщения, где /summary стоит не в начале (например "@bot /summary" или текст + /summary)
async def fallback_summary_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if int(update.effective_chat.id) != CHAT_ID:
        return
    text = (update.effective_message and update.effective_message.text) or ""
    low = text.lower()

    if "/summary" in low:
        # попытаемся выцепить аргумент (например "/summary 16-20")
        arg = None
        parts = low.split()
        for i, p in enumerate(parts):
            if p.startswith("/summary"):
                if i + 1 < len(parts):
                    cand = parts[i + 1].strip()
                    if cand in ("08-16", "16-20", "20-08", "night"):
                        arg = cand
                break
        await _do_summary(arg, ctx)

# ------- СТАРТ -------
async def main():
    if not TOKEN or CHAT_ID == 0:
        raise RuntimeError("BOT_TOKEN/CHAT_ID/TIMEZONE not set in Railway Variables.")

    await init_db()

    app = (Application.builder()
           .token(TOKEN)
           .rate_limiter(AIORateLimiter())
           .build())

    # собираем лиды
    app.add_handler(MessageHandler(filters.Chat(CHAT_ID) & (filters.TEXT | filters.CAPTION), on_any))
    app.add_handler(MessageHandler(filters.ChatType.CHANNEL & (filters.TEXT | filters.CAPTION), on_any))

    # команды: обычная команда + фолбек-текст
    app.add_handler(CommandHandler("summary", cmd_summary))            # без фильтра, но внутри проверяем CHAT_ID
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, fallback_summary_text))

    # расписание через tzinfo
    app.job_queue.run_daily(send_16, time(16, 0, tzinfo=TZ))
    app.job_queue.run_daily(send_20, time(20, 0, tzinfo=TZ))
    app.job_queue.run_daily(send_08, time(8,  0, tzinfo=TZ))

    # корректный цикл (без run_polling() внутри asyncio.run)
    await app.initialize()
    await app.start()
    try:
        await app.updater.start_polling(allowed_updates=Update.ALL_TYPES)
        await asyncio.Event().wait()
    finally:
        await app.updater.stop()
        await app.stop()
        await app.shutdown()

if __name__ == "__main__":
    asyncio.run(main())
