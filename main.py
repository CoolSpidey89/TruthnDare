from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters
import random
import os

# Sample questions
TRUTHS = [
    "What’s your biggest secret?",
    "What's the weirdest dream you’ve ever had?",
    "Who do you have a crush on right now?"
]

DARES = [
    "Do 10 pushups and send a selfie!",
    "Talk like a baby for 2 minutes!",
    "Change your profile pic to something funny!"
]

# Start command
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 Hey! I'm TruthieBot.\nUse /truthordare to start playing Truth or Dare!")

# Game start
async def truth_or_dare(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user.first_name
    await update.message.reply_text(f"{user}, Truth or Dare? Reply with 'truth' or 'dare'.")

# Handle player answer
async def handle_response(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.lower()
    if "truth" in text:
        await update.message.reply_text(random.choice(TRUTHS))
    elif "dare" in text:
        await update.message.reply_text(random.choice(DARES))
    else:
        await update.message.reply_text("Please reply with 'truth' or 'dare'.")

# Main app
if __name__ == '__main__':
    TOKEN = os.getenv("BOT_TOKEN")  # Koyeb will set this in env vars
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("truthordare", truth_or_dare))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_response))

    app.run_polling()
