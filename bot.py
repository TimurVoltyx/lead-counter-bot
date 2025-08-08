# ВРЕМЕННАЯ ВЕРСИЯ — только для получения CHAT_ID
import asyncio, re, os, aiosqlite, pytz
from datetime import datetime, time
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes, AIORateLimiter

print("Бот запущен, жду сообщений...")

TOKEN   = os.getenv("BOT_TOKEN")
CHAT_ID = int(os.getenv("CHAT_ID", "0")) if os.getenv("CHAT_ID") else None
TZ      = pytz.timezone(os.getenv("TIMEZONE","America/Los_Angeles"))

async def on_any(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    print("CHAT_ID:", update.effective_chat.id)
    await ctx.bot.send_message(chat_id=update.effective_chat.id, text=f"Ваш CHAT_ID: {update.effective_chat.id}")

async def main():
    if not TOKEN:
        raise RuntimeError("BOT_TOKEN не задан")
    app = (Application.builder()
           .token(TOKEN)
           .rate_limiter(AIORateLimiter())
           .build())
    app.add_handler(MessageHandler(filters.ALL, on_any))
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
