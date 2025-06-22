from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)
from telegram.constants import ChatType
import random
import os

# Questions
TRUTHS = [
    "What’s your biggest secret?",
    "What's a lie you've told recently?",
    "Who was your first crush?",
]

DARES = [
    "Sing a song and send it!",
    "Do 10 jumping jacks now!",
    "Change your bio to 'I'm a potato 🥔' for 10 minutes.",
]

LOBBY_TIMEOUT = 30  # seconds for lobby open
TURN_TIMEOUT = 30   # seconds per turn


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Hey! I'm TruthieBot!\n"
        "Use /startgame to start a Truth or Dare game in your group."
    )


async def start_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if chat.type not in [ChatType.GROUP, ChatType.SUPERGROUP]:
        await update.message.reply_text("⚠️ This command only works in groups.")
        return

    if context.chat_data.get("in_game", False):
        await update.message.reply_text("⚠️ A game is already in progress!")
        return

    context.chat_data["lobby"] = set()
    context.chat_data["in_game"] = False
    context.chat_data["players"] = []
    context.chat_data["current_turn"] = 0
    context.chat_data["active_user"] = None
    context.chat_data["eliminated"] = set()

    await update.message.reply_text(
        f"🎮 Game lobby is now OPEN! Players, type /join to enter. You have {LOBBY_TIMEOUT} seconds..."
    )

    context.job_queue.run_once(close_lobby, LOBBY_TIMEOUT, chat_id=chat.id)


async def join_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    lobby = context.chat_data.get("lobby")

    if lobby is None:
        await update.message.reply_text(
            "❌ No active game lobby. Wait for the host to start with /startgame."
        )
        return

    if (user.id, user.first_name) in lobby:
        await update.message.reply_text(f"✅ {user.first_name}, you are already in the lobby.")
        return

    lobby.add((user.id, user.first_name))
    await update.message.reply_text(f"✅ {user.first_name} joined the game!")


async def close_lobby(context: ContextTypes.DEFAULT_TYPE):
    chat_id = context.job.chat_id
    lobby = context.chat_data.get("lobby", set())

    if not lobby:
        await context.bot.send_message(chat_id, "❌ No players joined. Game cancelled.")
        context.chat_data["in_game"] = False
        context.chat_data["lobby"] = None
        return

    players = list(lobby)
    random.shuffle(players)
    context.chat_data["players"] = players
    context.chat_data["current_turn"] = 0
    context.chat_data["in_game"] = True
    context.chat_data["lobby"] = None
    context.chat_data["eliminated"] = set()

    player_names = ", ".join(name for _, name in players)
    await context.bot.send_message(chat_id, f"🚀 Game starting!\nPlayers: {player_names}")

    await ask_truth_or_dare(context, chat_id)


async def ask_truth_or_dare(context: ContextTypes.DEFAULT_TYPE, chat_id):
    players = context.chat_data.get("players")
    eliminated = context.chat_data.get("eliminated", set())
    current_turn = context.chat_data.get("current_turn", 0)

    # Skip eliminated players
    while current_turn < len(players) and players[current_turn][0] in eliminated:
        current_turn += 1

    if current_turn >= len(players):
        # Game over — check if anyone left
        alive_players = [p for p in players if p[0] not in eliminated]
        if alive_players:
            winners = ", ".join(name for _, name in alive_players)
            await context.bot.send_message(chat_id, f"🏆 Game over! Winners: {winners}")
        else:
            await context.bot.send_message(chat_id, "🏁 Game over! No winners, all eliminated.")
        context.chat_data["in_game"] = False
        context.chat_data["active_user"] = None
        return

    # Update current turn
    context.chat_data["current_turn"] = current_turn

    user_id, name = players[current_turn]
    keyboard = [
        [
            InlineKeyboardButton("🧠 Truth", callback_data="truth"),
            InlineKeyboardButton("🎯 Dare", callback_data="dare"),
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await context.bot.send_message(
        chat_id,
        f"🎲 It's {name}'s turn! Choose:",
        reply_markup=reply_markup,
    )

    context.chat_data["active_user"] = user_id

    # Schedule turn timeout job
    context.job_queue.run_once(turn_timeout, TURN_TIMEOUT, chat_id=chat_id)


async def turn_timeout(context: ContextTypes.DEFAULT_TYPE):
    chat_id = context.job.chat_id
    active_user = context.chat_data.get("active_user")
    players = context.chat_data.get("players", [])
    eliminated = context.chat_data.get("eliminated", set())

    if active_user is None:
        return  # no active player

    # Eliminate current player for timeout
    name = next((n for uid, n in players if uid == active_user), "Unknown")
    eliminated.add(active_user)
    context.chat_data["eliminated"] = eliminated

    await context.bot.send_message(chat_id, f"⏰ {name} took too long and is eliminated! ❌")

    # Move to next turn
    context.chat_data["current_turn"] += 1
    context.chat_data["active_user"] = None
    await ask_truth_or_dare(context, chat_id)


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    await query.answer()

    active_user = context.chat_data.get("active_user")
    if user_id != active_user:
        await query.answer("⏳ Please wait for your turn!", show_alert=True)
        return

    # Cancel turn timeout job to prevent elimination
    current_jobs = context.job_queue.get_jobs_by_name("turn_timeout")
    for job in current_jobs:
        job.schedule_removal()

    if query.data == "truth":
        await query.edit_message_text(f"🧠 Truth: {random.choice(TRUTHS)}")
    elif query.data == "dare":
        await query.edit_message_text(f"🎯 Dare: {random.choice(DARES)}")

    # Move to next turn
    context.chat_data["current_turn"] += 1
    context.chat_data["active_user"] = None
    chat_id = query.message.chat_id
    await ask_truth_or_dare(context, chat_id)


if __name__ == "__main__":
    TOKEN = os.getenv("BOT_TOKEN")
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("startgame", start_game))
    app.add_handler(CommandHandler("join", join_game))
    app.add_handler(CallbackQueryHandler(button_handler))

    app.run_polling()
