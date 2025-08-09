import os, re, logging
from datetime import datetime, time, timedelta
from urllib.parse import urlparse
from collections import defaultdict

import pytz
from telegram import Update
from telegram.ext import ApplicationBuilder, AIORateLimiter, CommandHandler, MessageHandler, ContextTypes, filters

# ---------- LOG ----------
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(name)s | %(message)s")
log = logging.getLogger("lead-counter-bot")

# ---------- ENV ----------
BOT_TOKEN   = os.getenv("BOT_TOKEN", "").strip()
CHAT_ID     = int(os.getenv("CHAT_ID", "0").strip() or "0")
TZ_NAME     = os.getenv("TIMEZONE", "America/Los_Angeles").strip()
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "").strip()
PORT        = int(os.getenv("PORT", "8080"))

if not BOT_TOKEN or not CHAT_ID or not WEBHOOK_URL:
    raise RuntimeError("Set BOT_TOKEN, CHAT_ID, WEBHOOK_URL in Railway Variables")

try:
    TZ = pytz.timezone(TZ_NAME)
except Exception:
    TZ = pytz.timezone("America/Los_Angeles")

def now() -> datetime:
    return datetime.now(TZ)

def window_name(dt: datetime) -> str:
    t = dt.time()
    if time(8,0)  <= t < time(16,0): return "08-16"
    if time(16,0) <= t < time(20,0): return "16-20"
    return "20-08"

def window_date_key(dt: datetime) -> str:
    # Ночь (00:00–07:59) относится к прошлому дню (окну 20-08)
    d = dt.date()
    if window_name(dt) == "20-08" and dt.time() < time(8,0):
        d = d - timedelta(days=1)
    return d.strftime("%Y-%m-%d")

# ---------- КЛАССИФИКАЦИЯ ----------
CATS = {
    "Angi leads": [r"\bangi\b", r"\bangi\s+leads?\b"],
    "Yelp leads": [r"\byelp\b", r"\byelp\s+leads?\b"],
    "Website":    [r"\bwebsite\b", r"\b(site|web)\s?form\b"],
    "Local":      [r"\blocal\b", r"\bgoogle\s?(ads|maps)?\b"],
}
LEAD_TRIGGERS = [r"\byou have received a new project request\b", r"\bnew project request\b", r"\blead\b"]

def classify(text: str) -> str | None:
    t = (text or "").lower()
    # если явный триггер лида — пытаемся поймать источник
    if any(re.search(p, t) for p in LEAD_TRIGGERS) or any(re.search(p, t) for pats in CATS.values() for p in pats):
        for name, pats in CATS.items():
            for p in pats:
                if re.search(p, t):
                    return name
        # если источник не распознан, сваливаем в Website по умолчанию
        return "Website"
    return None

# ---------- ПАМЯТЬ СЧЁТЧИКОВ ----------
# counts[date_key][window][category] = int
counts: dict[str, dict[str, dict[str, int]]] = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))

def bump_counter(text: str):
    cat = classify(text)
    if not cat:
        return False
    dt = now()
    dk = window_date_key(dt)
    wn = window_name(dt)
    counts[dk][wn][cat] += 1
    return True

# ---------- HANDLERS ----------
async def on_any(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not update.effective_chat or update.effective_chat.id != CHAT_ID:
        return
    msg = update.effective_message or update.channel_post
    text = (msg.text or msg.caption or "").strip()
    if not text:
        return
    hit = bump_counter(text)
    if hit:
        # лёгкое подтверждение, без спама
        try:
            await ctx.bot.send_message(CHAT_ID, "✅ Lead counted")
        except Exception as e:
            log.warning("confirm send failed: %s", e)

def last_window_and_date(dt: datetime) -> tuple[str, str]:
    t = dt.time()
    if t < time(8,0):  return "20-08", (dt.date() - timedelta(days=1)).strftime("%Y-%m-%d")
    if t < time(16,0): return "08-16", dt.date().strftime("%Y-%m-%d")
    if t < time(20,0): return "16-20", dt.date().strftime("%Y-%m-%d")
    return "20-08", dt.date().strftime("%Y-%m-%d")

async def cmd_summary(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not update.effective_chat or update.effective_chat.id != CHAT_ID:
        return
    arg = (ctx.args[0].lower() if ctx.args else None)
    if arg in ("08-16","16-20","20-08","night"):
        w = "20-08" if arg == "night" else arg
        dk = (now().date() - timedelta(days=1)).strftime("%Y-%m-%d") if w == "20-08" else now().date().strftime("%Y-%m-%d")
    else:
        w, dk = last_window_and_date(now())

    table = counts.get(dk, {}).get(w, {})
    total = sum(table.values())
    lines = [f"📊 Summary {dk} {w} — total: {total}"]
    if table:
        for cat, cnt in sorted(table.items(), key=lambda x: -x[1]):
            lines.append(f"• {cat}: {cnt}")
    else:
        lines.append("• No matches.")
    lines.append("Hey operators, any more leads? Please double-check!")
    await ctx.bot.send_message(CHAT_ID, "\n".join(lines))

async def cmd_ping(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat and update.effective_chat.id == CHAT_ID:
        await update.effective_message.reply_text("pong")

# ---------- MAIN ----------
def main():
    app = (
        ApplicationBuilder()
        .token(BOT_TOKEN)
        .rate_limiter(AIORateLimiter())
        .build()
    )

    # команды
    app.add_handler(CommandHandler("summary", cmd_summary))
    app.add_handler(CommandHandler("ping", cmd_ping))

    # все входящие из целевого чата
    app.add_handler(MessageHandler(filters.Chat(CHAT_ID) & (filters.TEXT | filters.CAPTION), on_any))

    # вебхук (URL уже поставлен в Telegram)
    hook_path = urlparse(WEBHOOK_URL).path or "/hook-1111"
    logging.info("Running webhook at 0.0.0.0:%s path=%s url=%s", PORT, hook_path, WEBHOOK_URL)
    app.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        url_path=hook_path.lstrip("/"),
        webhook_url=None,
        stop_signals=None,
    )

if __name__ == "__main__":
    main()
