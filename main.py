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
TOTAL_ROUNDS = 3   # total rounds in game


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

    context.chat_data.update({
        "lobby": set(),
        "in_game": False,
        "players": [],
        "current_turn": 0,
        "active_user": None,
        "eliminated": set(),
        "scores": {},
        "round": 1,
    })

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


async def quit_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    players = context.chat_data.get("players", [])
    eliminated = context.chat_data.get("eliminated", set())
    in_game = context.chat_data.get("in_game", False)

    if not in_game:
        await update.message.reply_text("❌ No game in progress to quit.")
        return

    # Check if user is playing and not eliminated
    player_ids = [uid for uid, _ in players]
    if user.id not in player_ids:
        await update.message.reply_text("❌ You are not part of the current game.")
        return

    if user.id in eliminated:
        await update.message.reply_text("❌ You are already eliminated.")
        return

    eliminated.add(user.id)
    context.chat_data["eliminated"] = eliminated

    await update.message.reply_text(f"⚠️ {user.first_name} has quit and is eliminated from the game!")

    # If quitting player is the active user, move to next turn immediately
    if context.chat_data.get("active_user") == user.id:
        context.chat_data["current_turn"] += 1
        context.chat_data["active_user"] = None
        chat_id = update.effective_chat.id
        await ask_truth_or_dare(context, chat_id)


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
    context.chat_data["scores"] = {uid: 0 for uid, _ in players}
    context.chat_data["round"] = 1

    player_names = ", ".join(name for _, name in players)
    await context.bot.send_message(chat_id, f"🚀 Game starting!\nPlayers: {player_names}\nRounds: {TOTAL_ROUNDS}")

    await ask_truth_or_dare(context, chat_id)


async def ask_truth_or_dare(context: ContextTypes.DEFAULT_TYPE, chat_id):
    players = context.chat_data.get("players")
    eliminated = context.chat_data.get("eliminated", set())
    current_turn = context.chat_data.get("current_turn", 0)
    round_num = context.chat_data.get("round", 1)

    # Skip eliminated players
    while current_turn < len(players) and players[current_turn][0] in eliminated:
        current_turn += 1

    if current_turn >= len(players):
        # End of round
        alive_players = [p for p in players if p[0] not in eliminated]

        if len(alive_players) == 0:
            # Everyone eliminated
            await context.bot.send_message(chat_id, "🏁 Game over! Everyone was eliminated. No winners.")
            context.chat_data["in_game"] = False
            context.chat_data["active_user"] = None
            return

        if round_num >= TOTAL_ROUNDS or len(alive_players) == 1:
            # Game end - announce winners
            max_score = max(context.chat_data["scores"].values())
            winners = [name for uid, name in players if context.chat_data["scores"].get(uid, 0) == max_score and uid not in eliminated]

            scores_text = "\n".join(
                f"{name}: {context.chat_data['scores'].get(uid, 0)} points" for uid, name in players if uid not in eliminated
            )

            winner_text = ", ".join(winners)
            await context.bot.send_message(
                chat_id,
                f"🏆 Game over!\nWinner(s): {winner_text}\n\nFinal Scores:\n{scores_text}",
            )
            context.chat_data["in_game"] = False
            context.chat_data["active_user"] = None
            return

        # Next round
        context.chat_data["round"] = round_num + 1
        context.chat_data["current_turn"] = 0
        await context.bot.send_message(chat_id, f"➡️ Starting Round {context.chat_data['round']}!")
        current_turn = 0

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
        f"🎲 Round {round_num} - It's {name}'s turn! Choose:",
        reply_markup=reply_markup,
    )

    context.chat_data["active_user"] = user_id

    # Schedule turn timeout job (named for easy cancel)
    context.job_queue.run_once(turn_timeout, TURN_TIMEOUT, chat_id=chat_id, name=f"turn_timeout_{user_id}")


async def turn_timeout(context: ContextTypes.DEFAULT_TYPE):
    chat_id = context.job.chat_id
    job_name = context.job.name  # e.g. "turn_timeout_12345678"
    user_id = int(job_name.split("_")[-1])

    eliminated = context.chat_data.get("eliminated", set())
    players = context.chat_data.get("players", [])

    if user_id in eliminated:
        return  # Already eliminated

    name = next((n for uid, n in players if uid == user_id), "Unknown")
    eliminated.add(user_id)
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

    # Cancel turn timeout job for this user
    job_name = f"turn_timeout_{user_id}"
    current_jobs = context.job_queue.get_jobs_by_name(job_name)
    for job in current_jobs:
        job.schedule_removal()

    if query.data == "truth":
        await query.edit_message_text(f"🧠 Truth: {random.choice(TRUTHS)}

