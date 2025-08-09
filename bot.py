import os
import logging
import sqlite3
import pytz
from datetime import datetime
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# ---------------- CONFIG ----------------
TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = int(os.getenv("CHAT_ID", "0"))
TIMEZONE = os.getenv("TIMEZONE", "UTC")
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "")
PORT = int(os.getenv("PORT", "8080"))
URL_PATH = os.getenv("URL_PATH", f"{TOKEN}")

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

DB_FILE = "leads.db"

# --------------- DB INIT -----------------
def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute(
        """CREATE TABLE IF NOT EXISTS leads (
               id INTEGER PRIMARY KEY AUTOINCREMENT,
               user_id INTEGER,
               username TEXT,
               full_name TEXT,
               message TEXT,
               date TEXT
           )"""
    )
    conn.commit()
    conn.close()

# --------------- HANDLERS ----------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Lead Counter Bot is running ✅")

async def summary(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM leads")
    total = c.fetchone()[0]
    conn.close()
    await update.message.reply_text(f"📊 Total leads: {total}")

async def new_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    text = update.message.text or ""
    tz = pytz.timezone(TIMEZONE)
    now = datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S")

    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute(
        "INSERT INTO leads (user_id, username, full_name, message, date) VALUES (?, ?, ?, ?, ?)",
        (user.id, user.username, user.full_name, text, now),
    )
    conn.commit()
    conn.close()

    await context.bot.send_message(
        chat_id=CHAT_ID,
        text=f"📥 New lead from {user.full_name} (@{user.username}):\n{text}",
    )

# --------------- BUILD APP ----------------
def build_app():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("summary", summary))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, new_message))
    return app

# --------------- ENTRY ----------------
if __name__ == "__main__":
    if not TOKEN or CHAT_ID == 0 or not WEBHOOK_URL:
        raise RuntimeError("Set BOT_TOKEN, CHAT_ID, TIMEZONE, WEBHOOK_URL in Railway Variables.")

    init_db()

    app = build_app()

    # Фикс отсутствующего event loop
    import asyncio
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    logger.info(f"Starting webhook on port {PORT}, path /{URL_PATH}")
    app.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        url_path=URL_PATH,
        webhook_url=WEBHOOK_URL,
    )
