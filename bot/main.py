import os
import logging
from fastapi import FastAPI, Request, Response, status
from telegram import Update, Bot
from telegram.ext import ApplicationBuilder

from .bot_handler import get_handlers  # Adjust import if needed

from telegram.ext import ContextTypes

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error(msg="Exception while handling update:", exc_info=context.error)

application.add_error_handler(error_handler)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")

if not BOT_TOKEN:
    raise RuntimeError("Please set the BOT_TOKEN environment variable")
if not WEBHOOK_URL:
    raise RuntimeError("Please set the WEBHOOK_URL environment variable")

app = FastAPI()
bot = Bot(token=BOT_TOKEN)
application = ApplicationBuilder().token(BOT_TOKEN).build()

# Register handlers from bot_handler.py
for handler in get_handlers():
    application.add_handler(handler)

@app.get("/")
async def root():
    return {"message": "Truth or Dare Telegram Bot is running!"}

@app.get("/health")
async def health_check():
    return {"status": "ok"}

@app.on_event("startup")
async def on_startup():
    logger.info("Starting Telegram Bot...")

    await application.initialize()
    await application.start()
    await bot.initialize()

    webhook_full_url = f"{WEBHOOK_URL}"
    await bot.set_webhook(webhook_full_url)

    logger.info(f"✅ Webhook set to: {webhook_full_url}")
    logger.info("🚀 Bot is up and running!")

    
    
@app.post("/webhook")
async def telegram_webhook(request: Request):
    try:
        json_update = await request.json()
        update = Update.de_json(json_update, bot)
        await application.process_update(update)
        return Response(status_code=status.HTTP_200_OK)
    except Exception as e:
        logger.error(f"Error handling update: {e}")
        return Response(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)

