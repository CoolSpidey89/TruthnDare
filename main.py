from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes
)
import random
import os

# Truth and Dare Questions
TRUTHS = [
    "What’s your biggest secret?",
    "What's a lie you've told recently?",
    "Who was your first crush?"
]

DARES = [
    "Sing a song and send it!",
    "Do 10 jumping jacks now!",
    "Change your bio to 'I'm a potato 🥔' for 10 minutes."
]

# /start command
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 Hey! I'm TruthieBot!\nUse /truthordare to play.")

# /truthordare command with inline buttons
async def truth_or_dare(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user.first_name

    keyboard = [
        [
            InlineKeyboardButton("🧠 Truth", callback_data="truth"),
            InlineKeyboardButton("🎯 Dare", callback_data="dare")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        f"{user}, choose Truth or Dare:",
        reply_markup=reply_markup
    )

# Handle button presses
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()  # Acknowledge the button press

    if query.data == "truth":
        await query.edit_message_text(f"🧠 Truth: {random.choice(TRUTHS)}")
    elif query.data == "dare":
        await query.edit_message_text(f"🎯 Dare: {random.choice(DARES)}")

# Main app
if __name__ == '__main__':
    TOKEN = os.getenv("BOT_TOKEN")
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("truthordare", truth_or_dare))
    app.add_handler(CallbackQueryHandler(button_handler))

    app.run_polling()
