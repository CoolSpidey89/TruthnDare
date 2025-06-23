import os
import logging
from fastapi import FastAPI, Request, Response, status
from telegram import Update, Bot
from telegram.ext import ApplicationBuilder, ContextTypes

from bot_handler import get_handlers

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN")  # Set your Telegram bot token in environment variable

if not BOT_TOKEN:
    raise RuntimeError("Please set the BOT_TOKEN environment variable")

app = FastAPI()
bot = Bot(token=BOT_TOKEN)
application = ApplicationBuilder().token(BOT_TOKEN).build()

# Add handlers to the application
for handler in get_handlers():
    application.add_handler(handler)


@app.on_event("startup")
async def on_startup():
    # This will start the bot polling or webhook depending on setup
    logger.info("Starting Telegram Bot...")


@app.post("/webhook")
async def telegram_webhook(request: Request):
    """Receive updates from Telegram via webhook and process them."""
    try:
        json_update = await request.json()
        update = Update.de_json(json_update, bot)

        await application.process_update(update)
        return Response(status_code=status.HTTP_200_OK)
    except Exception as e:
        logger.error(f"Error handling update: {e}")
        return Response(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)


@app.get("/")
async def root():
    return {"message": "Truth or Dare Telegram Bot is running!"}
