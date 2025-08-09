# lead-counter-bot (WEBHOOK): 08–16, 16–20, 20–08 + /summary + jokes
import asyncio, os, re, random, aiosqlite, pytz
from datetime import datetime, time, timedelta
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, AIORateLimiter, filters

TOKEN   = os.getenv("BOT_TOKEN")
CHAT_ID = int(os.getenv("CHAT_ID", "0"))
TZ      = pytz.timezone(os.getenv("TIMEZONE", "America/Los_Angeles"))
DB = "counts.sqlite3"

WEBHOOK_URL = os.getenv("WEBHOOK_URL")  # e.g. https://...railway.app/hook-1111
PORT   = int(os.getenv("PORT", "8080"))
URL_PATH = WEBHOOK_URL.rstrip("/").split("/")[-1]

CATS = {
    "Angi leads": [r"\bangi\b", r"\bangi\s+leads?\b"],
    "Yelp leads": [r"\byelp\b", r"\byelp\s+leads?\b"],
    "Website":    [r"\bwebsite\b", r"\b(site|web)\s?form\b"],
    "Local":      [r"\blocal\b", r"\bgoogle\s?(ads|maps)?\b"],
}
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

def now() -> datetime: return datetime.now(TZ)
def window_name(dt: datetime) -> str:
    t = dt.time()
    if time(8,0) <= t < time(16,0): return "08-16"
    if time(16,0) <= t < time(20,0): return "16-20"
    return "20-08"
def window_key_date(dt: datetime) -> str:
    w = window_name(dt); d = dt.date()
    if w == "20-08" and dt.time() < time(8,0): d = d - timedelta(days=1)
    return d.strftime("%Y-%m-%d")

async def init_db():
    async with aiosqlite.connect(DB) as db:
        await db.execute("""CREATE TABLE IF NOT EXISTS counts(
            chat_id INTEGER, date TEXT, window TEXT, category TEXT, cnt INTEGER,
            PRIMARY KEY(chat_id, date, window, category))""")
        await db.commit()

def classify(text: str) -> str | None:
    t = (text or "").lower()
    for name, pats in CATS.items():
        for p in pats:
            if re.search(p, t): return name
    return None

async def bump(cat: str, dt: datetime):
    d = window_key_date(dt); w = window_name(dt)
    async with aiosqlite.connect(DB) as db:
        await db.execute("""INSERT INTO counts(chat_id,date,window,category,cnt)
            VALUES(?,?,?,?,1)
            ON CONFLICT(chat_id,date,window,category) DO UPDATE SET cnt=cnt+1
        """, (CHAT_ID, d, w, cat)); await db.commit()

async def on_any(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not update.effective_chat or int(update.effective_chat.id) != CHAT_ID: return
    msg = update.effective_message or update.channel_post
    text = (msg and (msg.text or msg.caption)) or ""
    cat = classify(text)
    if cat: await bump(cat, now())

async def summary_for(window: str, date_key: str) -> str:
    async with aiosqlite.connect(DB) as db:
        cur = await db.execute("""SELECT category,cnt FROM counts
            WHERE chat_id=? AND date=? AND window=? ORDER BY cnt DESC""",
            (CHAT_ID, date_key, window))
        rows = await cur.fetchall()
    total = sum(c for _,c in rows)
    lines = [f"📊 Summary {date_key} {window} — total: {total}"]
    lines += [f"• {cat}: {cnt}" for cat,cnt in rows] or ["• No matches."]
    lines.append("Hey operators, any more leads? Please double-check!")
    return "\n".join(lines)

async def send_joke(ctx: ContextTypes.DEFAULT_TYPE):
    await ctx.bot.send_message(CHAT_ID, random.choice(JOKES))

async def send_16(ctx: ContextTypes.DEFAULT_TYPE):
    await ctx.bot.send_message(CHAT_ID, await summary_for("08-16", now().date().strftime("%Y-%m-%d"))); await send_joke(ctx)
async def send_20(ctx: ContextTypes.DEFAULT_TYPE):
    await ctx.bot.send_message(CHAT_ID, await summary_for("16-20", now().date().strftime("%Y-%m-%d"))); await send_joke(ctx)
async def send_08(ctx: ContextTypes.DEFAULT_TYPE):
    await ctx.bot.send_message(CHAT_ID, await summary_for("20-08", (now().date()-timedelta(days=1)).strftime("%Y-%m-%d"))); await send_joke(ctx)

def last_window_and_date(dt: datetime) -> tuple[str,str]:
    t = dt.time()
    if t < time(8,0): return "20-08", (dt.date()-timedelta(days=1)).strftime("%Y-%m-%d")
    if t < time(16,0): return "08-16", dt.date().strftime("%Y-%m-%d")
    if t < time(20,0): return "16-20", dt.date().strftime("%Y-%m-%d")
    return "20-08", dt.date().strftime("%Y-%m-%d")

async def _do_summary(arg: str|None, ctx: ContextTypes.DEFAULT_TYPE):
    w, d = (("20-08", (now().date()-timedelta(days=1)).strftime("%Y-%m-%d"))
            if (arg=="20-08" or arg=="night") else
            ((arg, now().date().strftime("%Y-%m-%d")) if arg in ("08-16","16-20") else last_window_and_date(now())))
    await ctx.bot.send_message(CHAT_ID, await summary_for(w, d)); await send_joke(ctx)

async def cmd_summary(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if int(update.effective_chat.id) != CHAT_ID: return
    await _do_summary((ctx.args[0].lower() if ctx.args else None), ctx)

async def fallback_summary_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if int(update.effective_chat.id) != CHAT_ID: return
    text = (update.effective_message and update.effective_message.text) or ""
    if not text: return
    low = text.lower()
    if "/summary" in low:
        arg = None
        parts = low.split()
        for i,p in enumerate(parts):
            if p.startswith("/summary") and i+1 < len(parts):
                cand = parts[i+1].strip()
                if cand in ("08-16","16-20","20-08","night"): arg=cand
                break
        await _do_summary(arg, ctx)

async def main():
    if not TOKEN or CHAT_ID==0 or not WEBHOOK_URL: raise RuntimeError("Set BOT_TOKEN, CHAT_ID, TIMEZONE, WEBHOOK_URL")

    await init_db()
    app = (Application.builder().token(TOKEN).rate_limiter(AIORateLimiter()).build())

    # handlers
    app.add_handler(CommandHandler("summary", cmd_summary))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, fallback_summary_text))
    app.add_handler(MessageHandler(filters.Chat(CHAT_ID) & (filters.TEXT | filters.CAPTION), on_any))
    app.add_handler(MessageHandler(filters.ChatType.CHANNEL & (filters.TEXT | filters.CAPTION), on_any))

    # jobs
    app.job_queue.run_daily(send_16, time(16,0, tzinfo=TZ))
    app.job_queue.run_daily(send_20, time(20,0, tzinfo=TZ))
    app.job_queue.run_daily(send_08, time(8, 0, tzinfo=TZ))

    await app.initialize()
    # health endpoint (чтобы видеть 200/OK):
    app.web_app.router.add_get("/health", lambda r: app.web_app_response(text="OK"))

    # webhook
    await app.bot.set_webhook(url=WEBHOOK_URL, drop_pending_updates=True)
    await app.start()
    await app.start_webhook(listen="0.0.0.0", port=PORT, url_path=URL_PATH, webhook_url=WEBHOOK_URL)

    try:
        await asyncio.Event().wait()
    finally:
        await app.stop()
        await app.shutdown()

if __name__ == "__main__":
    asyncio.run(main())
