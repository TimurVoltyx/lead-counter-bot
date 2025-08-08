import logging
import asyncio
from datetime import datetime, time, timedelta
import pytz
import random
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters

# === НАСТРОЙКИ ===
BOT_TOKEN = "ТОКЕН_ОТ_BOTFATHER"  # <-- сюда токен без @
CHAT_ID = -1002485440713  # id чата
TZ = pytz.timezone("America/Los_Angeles")

# Логирование
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)

# === Вспомогательные функции ===
def last_window_and_date(dt: datetime) -> tuple[str, str]:
    t = dt.time()
    if t < time(8,0):           # 00:00–07:59
        return "20-08", (dt.date() - timedelta(days=1)).strftime("%Y-%m-%d")
    if t < time(16,0):          # 08:00–15:59
        return "08-16", dt.date().strftime("%Y-%m-%d")
    if t < time(20,0):          # 16:00–19:59
        return "16-20", dt.date().strftime("%Y-%m-%d")
    return "20-08", dt.date().strftime("%Y-%m-%d")  # 20:00–23:59

# Список шуточных фраз
jokes = [
    "Hey team, are you still alive? What's the Volty conversion?",
    "Knock-knock! Anyone counting the Volty leads today?",
    "Wake up, operators! We need the conversion stats.",
    "If this chat was a lead, would you convert it? Give me numbers!",
    "Psst... conversion report, please? Don't make me send memes.",
    "Attention crew! Volty conversion check-in time!",
    "Do we have conversions or are they hiding?",
    "Yo! Operators! Numbers, please!",
    "Conversion fairy came? Show me the magic numbers.",
    "Lead report time! Who’s on duty?"
]

async def send_joke(app):
    msg = random.choice(jokes)
    await app.bot.send_message(chat_id=CHAT_ID, text=msg)

# === Хэндлеры ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Bot is running!")

async def handle_leads(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    await context.bot.send_message(chat_id=CHAT_ID, text=f"📢 Lead info received:\n{text}")
    await send_joke(context.application)

async def send_daily_summary(context: ContextTypes.DEFAULT_TYPE):
    now = datetime.now(TZ)
    window, date_str = last_window_and_date(now)
    await context.bot.send_message(chat_id=CHAT_ID, text=f"📊 Summary for {date_str}, window {window}")

async def manual_summary(update: Update, context: ContextTypes.DEFAULT_TYPE):
    now = datetime.now(TZ)
    window, date_str = last_window_and_date(now)
    await context.bot.send_message(chat_id=CHAT_ID, text=f"📊 Manual summary for {date_str}, window {window}")

# === Запуск бота ===
async def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("summary", manual_summary))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_leads))

    # Автосводки в 8:00, 16:00, 20:00
    app.job_queue.run_daily(send_daily_summary, time(hour=8, minute=0, tzinfo=TZ))
    app.job_queue.run_daily(send_daily_summary, time(hour=16, minute=0, tzinfo=TZ))
    app.job_queue.run_daily(send_daily_summary, time(hour=20, minute=0, tzinfo=TZ))

    await app.run_polling()

if __name__ == "__main__":
    asyncio.run(main())
