# Telegram lead counter bot: 3 отчёта в день (08-16, 16-20, 20-08)
# Категории по ключевым словам: Angi, Yelp, Website, Local
import asyncio, re, os, aiosqlite, pytz
from datetime import datetime, time
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes, AIORateLimiter

TOKEN   = os.getenv("BOT_TOKEN")
CHAT_ID = int(os.getenv("CHAT_ID", "0"))
TZ      = pytz.timezone(os.getenv("TIMEZONE","America/Los_Angeles"))

DB = "counts.sqlite3"

CATS = {
    "Angi leads":   [r"\bangi\b", r"\bangi leads?\b"],
    "Yelp leads":   [r"\byelp\b", r"\byelp leads?\b"],
    "Website":      [r"\bwebsite\b", r"\bsite form\b", r"\bweb\s?form\b"],
    "Local":        [r"\blocal\b", r"\bgoogle\s?(ads|maps)?\b", r"\blocally\b"],
}

def now_la(): return datetime.now(TZ)

def win_name(dt: datetime) -> str:
    t = dt.time()
    if time(8,0) <= t < time(16,0):  return "08-16"
    if time(16,0) <= t < time(20,0): return "16-20"
    return "20-08"

async def init_db():
    async with aiosqlite.connect(DB) as db:
        await db.execute("""
        CREATE TABLE IF NOT EXISTS counts(
            chat_id INTEGER,
            date TEXT,
            window TEXT,
            category TEXT,
            cnt INTEGER,
            PRIMARY KEY(chat_id, date, window, category)
        )""")
        await db.commit()

def classify(text: str) -> str | None:
    t = (text or "").lower()
    for name, rules in CATS.items():
        for r in rules:
            if re.search(r, t):
                return name
    return None

async def bump(cat: str, dt: datetime):
    d = dt.strftime("%Y-%m-%d")
    w = win_name(dt)
    async with aiosqlite.connect(DB) as db:
        await db.execute("""
            INSERT INTO counts(chat_id, date, window, category, cnt)
            VALUES(?, ?, ?, ?, 1)
            ON CONFLICT(chat_id, date, window, category)
            DO UPDATE SET cnt = cnt + 1
        """, (CHAT_ID, d, w, cat))
        await db.commit()

async def on_any(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not update.effective_chat or update.effective_chat.id != CHAT_ID:
        return
    text = (update.effective_message and (update.effective_message.text or update.effective_message.caption)) or \
           (update.channel_post and (update.channel_post.text or update.channel_post.caption)) or ""
    cat = classify(text)
    if cat:
        await bump(cat, now_la())

async def summary_for(window: str, day: datetime):
    d = day.strftime("%Y-%m-%d")
    async with aiosqlite.connect(DB) as db:
        cur = await db.execute("""
            SELECT category, cnt FROM counts
            WHERE chat_id=? AND date=? AND window=?
            ORDER BY cnt DESC
        """, (CHAT_ID, d, window))
        rows = await cur.fetchall()
    total = sum(c for _, c in rows)
    lines = [f"📊 Сводка {d} {window} (всего: {total})"]
    if rows:
        for cat, cnt in rows:
            lines.append(f"• {cat} — {cnt}")
    else:
        lines.append("• Лидов не найдено.")
    lines.append('Эй операторы, были ли еще лиды — проверяйте!')
    return "\n".join(lines)

async def send_16(ctx: ContextTypes.DEFAULT_TYPE):
    await ctx.bot.send_message(chat_id=CHAT_ID, text=await summary_for("08-16", now_la()))

async def send_20(ctx: ContextTypes.DEFAULT_TYPE):
    await ctx.bot.send_message(chat_id=CHAT_ID, text=await summary_for("16-20", now_la()))

async def send_08(ctx: ContextTypes.DEFAULT_TYPE):
    await ctx.bot.send_message(chat_id=CHAT_ID, text=await summary_for("20-08", now_la()))

async def main():
    if not TOKEN or not CHAT_ID:
        raise RuntimeError("BOT_TOKEN/CHAT_ID/TIMEZONE не заданы в переменных окружения.")
    await init_db()
    app = (Application.builder()
           .token(TOKEN)
           .rate_limiter(AIORateLimiter())
           .build())

    app.add_handler(MessageHandler(filters.Chat(CHAT_ID) & (filters.TEXT | filters.CAPTION), on_any))
    app.add_handler(MessageHandler(filters.UpdateType.CHANNEL_POST, on_any))

    app.job_queue.run_daily(send_16, time(16,0), timezone=TZ)
    app.job_queue.run_daily(send_20, time(20,0), timezone=TZ)
    app.job_queue.run_daily(send_08, time(8,0),  timezone=TZ)

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
