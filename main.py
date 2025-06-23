import os
import random
import asyncio

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)
from telegram.constants import ChatType
from http import HTTPStatus
from fastapi import FastAPI, Request, Response
import uvicorn

TOKEN = os.getenv("7977945135:AAHLNrUZYNwlItQlIvbcNjMhSy18Je25caM")
WEBHOOK_PATH = f"/webhook/7977945135:AAHLNrUZYNwlItQlIvbcNjMhSy18Je25caM"
WEBHOOK_URL = os.getenv("WEBHOOK_URL")  # Set to your Render service URL

# Replace your previous app-building code:
ptb = Application.builder().token(TOKEN).build()
ptb.add_handler(CommandHandler("start", start))
# ... add other handlers here ...

app = FastAPI()

@app.on_event("startup")
async def startup():
    await ptb.start()
    await ptb.bot.set_webhook(WEBHOOK_URL + WEBHOOK_PATH)

@app.post(WEBHOOK_PATH)
async def webhook(request: Request):
    data = await request.json()
    update = Update.de_json(data, ptb.bot)
    await ptb.process_update(update)
    return Response(status_code=HTTPStatus.OK)

@app.on_event("shutdown")
async def shutdown():
    await ptb.bot.delete_webhook()
    await ptb.stop()

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))

# Questions by difficulty level (expand later)
TRUTHS = {
    "easy": [
        "What's your favorite color?",
        "What's your biggest fear?",
        "Have you ever lied to your best friend?",
    ],
    "medium": [
        "What's your biggest secret?",
        "Who was your first crush?",
        "What's a lie you've told recently?",
    ],
    "spicy": [
        "What's your wildest fantasy?",
        "Have you ever skinny dipped?",
        "What's your most embarrassing intimate moment?",
    ],
}

DARES = {
    "easy": [
        "Do 10 jumping jacks.",
        "Sing a song and send it!",
        "Imitate your favorite celebrity for 15 seconds.",
    ],
    "medium": [
        "Change your bio to 'I'm a potato 🥔' for 10 minutes.",
        "Do a funny dance for 15 seconds.",
        "Send a silly selfie.",
    ],
    "spicy": [
        "Send a sultry selfie (safe for group).",
        "Do a sexy dance for 10 seconds on video.",
        "Text your crush something naughty.",
    ],
}

LOBBY_TIMEOUT = 30  # seconds for lobby open
TURN_TIMEOUT = 30   # seconds per turn
TOTAL_ROUNDS = 3    # total rounds per game


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Hey! I'm TruthieBot!\n"
        "Use /startgame [easy|medium|spicy] to start a Truth or Dare game.\n"
        "Players join with /join.\n"
        "Use /quit to leave mid-game.\n"
        "Use /status or /scoreboard to check game progress."
    )
async def start_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user

    if chat.type not in [ChatType.GROUP, ChatType.SUPERGROUP]:
        await update.message.reply_text("⚠️ This command only works in groups.")
        return

    if context.chat_data.get("in_game", False):
        await update.message.reply_text("⚠️ A game is already in progress!")
        return

    # Only admins can start game
    admins = await context.bot.get_chat_administrators(chat.id)
    admin_ids = [admin.user.id for admin in admins]
    if user.id not in admin_ids:
        await update.message.reply_text("❌ Only group admins can start a game.")
        return

    args = context.args
    difficulty = "medium"
    if args and args[0].lower() in ["easy", "medium", "spicy"]:
        difficulty = args[0].lower()

    context.chat_data.update({
        "lobby": set(),
        "in_game": False,
        "players": [],
        "current_turn": 0,
        "active_user": None,
        "eliminated": set(),
        "scores": {},
        "round": 1,
        "difficulty": difficulty,
        "host_id": user.id,
    })

    await update.message.reply_text(
        f"🎮 Game lobby is now OPEN! Players, type /join to enter. You have {LOBBY_TIMEOUT} seconds...\n"
        f"Difficulty set to *{difficulty.capitalize()}*.",
        parse_mode="Markdown",
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

    # If quitting user is current turn, advance turn immediately
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

    # Build mentions list for players
    mentions = []
    for user_id, first_name in players:
        try:
            user = await context.bot.get_chat_member(chat_id, user_id)
            username = user.user.username
        except Exception:
            username = None

        if username:
            mention = f"[@{username}](tg://user?id={user_id})"
        else:
            mention = f"[{first_name}](tg://user?id={user_id})"
        mentions.append(mention)

    player_mentions_text = ", ".join(mentions)
    difficulty = context.chat_data.get("difficulty", "medium")

    await context.bot.send_message(
        chat_id,
        f"🚀 Game starting at *{difficulty.capitalize()}* difficulty!\n"
        f"Players: {player_mentions_text}\n"
        f"Rounds: {TOTAL_ROUNDS}",
        parse_mode="Markdown",
    )

    await ask_truth_or_dare(context, chat_id)
async def ask_truth_or_dare(context: ContextTypes.DEFAULT_TYPE, chat_id):
    players = context.chat_data.get("players")
    eliminated = context.chat_data.get("eliminated", set())
    current_turn = context.chat_data.get("current_turn", 0)
    round_num = context.chat_data.get("round", 1)
    difficulty = context.chat_data.get("difficulty", "medium")

    # Skip eliminated players' turns
    while current_turn < len(players) and players[current_turn][0] in eliminated:
        current_turn += 1

    # Check if round ended or game over
    if current_turn >= len(players):
        alive_players = [p for p in players if p[0] not in eliminated]

        if len(alive_players) == 0:
            await context.bot.send_message(chat_id, "🏁 Game over! Everyone was eliminated. No winners.")
            context.chat_data["in_game"] = False
            context.chat_data["active_user"] = None
            return

        if round_num >= TOTAL_ROUNDS or len(alive_players) == 1:
            max_score = max(context.chat_data["scores"].values()) if context.chat_data["scores"] else 0
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

        # Start new round
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

    mention = f"[{name}](tg://user?id={user_id})"

    await context.bot.send_message(
        chat_id,
        f"🎲 Round {context.chat_data['round']} - It's {mention}'s turn! Choose:",
        reply_markup=reply_markup,
        parse_mode="Markdown",
    )

    context.chat_data["active_user"] = user_id

    # Cancel existing timeout jobs for this turn:
    for job in context.job_queue.get_jobs_by_name(f"turn_timeout_{chat_id}"):
        job.schedule_removal()

    # Schedule timeout for player response
    context.job_queue.run_once(
        timeout_player, TURN_TIMEOUT, chat_id=chat_id, name=f"turn_timeout_{chat_id}"
    )


async def timeout_player(context: ContextTypes.DEFAULT_TYPE):
    chat_id = context.job.chat_id
    active_user = context.chat_data.get("active_user")
    if active_user is None:
        return  # no active player, maybe game ended

    players = context.chat_data.get("players")
    eliminated = context.chat_data.get("eliminated", set())

    # Eliminate player who timed out
    eliminated.add(active_user)
    context.chat_data["eliminated"] = eliminated

    # Find mention for player
    mention = None
    for uid, name in players:
        if uid == active_user:
            mention = f"[{name}](tg://user?id={uid})"
            break

    await context.bot.send_message(
        chat_id,
        f"⏰ {mention if mention else 'Player'} took too long! Eliminated from the game.",
        parse_mode="Markdown",
    )

    # Move to next turn
    context.chat_data["current_turn"] += 1
    context.chat_data["active_user"] = None

    await ask_truth_or_dare(context, chat_id)


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user = query.from_user
    chat = query.message.chat
    data = query.data

    active_user = context.chat_data.get("active_user")
    if active_user != user.id:
        await query.edit_message_text("❌ It's not your turn!")
        return

    difficulty = context.chat_data.get("difficulty", "medium")
    players = context.chat_data.get("players", [])
    eliminated = context.chat_data.get("eliminated", set())
    scores = context.chat_data.get("scores", {})
    current_turn = context.chat_data.get("current_turn", 0)

    # Cancel timeout job for this turn
    for job in context.job_queue.get_jobs_by_name(f"turn_timeout_" + str(chat.id)):
        job.schedule_removal()

    question = None
    if data == "truth":
        question = random.choice(TRUTHS[difficulty])
    elif data == "dare":
        question = random.choice(DARES[difficulty])
    else:
        await query.edit_message_text("⚠️ Invalid choice.")
        return

    user_id, name = players[current_turn]
    mention = f"[{name}](tg://user?id={user_id})"

    await query.edit_message_text(
        f"👉 {mention}, your *{data.capitalize()}* is:\n\n_{question}_",
        parse_mode="Markdown",
    )

    # Score +1 for answering question
    scores[user_id] = scores.get(user_id, 0) + 1
    context.chat_data["scores"] = scores

    # Move to next turn
    context.chat_data["current_turn"] += 1
    context.chat_data["active_user"] = None

    # Wait 5 seconds before next turn question to give players time to read
    await asyncio.sleep(5)
    await ask_truth_or_dare(context, chat.id)


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    in_game = context.chat_data.get("in_game", False)
    if not in_game:
        await update.message.reply_text("❌ No game currently running.")
        return

    players = context.chat_data.get("players", [])
    eliminated = context.chat_data.get("eliminated", set())
    current_turn = context.chat_data.get("current_turn", 0)
    round_num = context.chat_data.get("round", 1)
    difficulty = context.chat_data.get("difficulty", "medium")

    alive = [name for uid, name in players if uid not in eliminated]
    eliminated_names = [name for uid, name in players if uid in eliminated]

    msg = (
        f"🎮 *Game Status*\n"
        f"Difficulty: *{difficulty.capitalize()}*\n"
        f"Round: *{round_num}*\n"
        f"Players still in game: {', '.join(alive)}\n"
        f"Eliminated players: {', '.join(eliminated_names) if eliminated_names else 'None'}"
    )

    await update.message.reply_text(msg, parse_mode="Markdown")


async def scoreboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    scores = context.chat_data.get("scores")
    players = context.chat_data.get("players", [])
    eliminated = context.chat_data.get("eliminated", set())

    if not scores:
        await update.message.reply_text("❌ No scores available. No game in progress?")
        return

    msg_lines = ["📊 *Scoreboard*:"]
    for uid, name in players:
        score = scores.get(uid, 0)
        status = "❌" if uid in eliminated else "✅"
        msg_lines.append(f"{name}: {score} points {status}")

    await update.message.reply_text("\n".join(msg_lines), parse_mode="Markdown")


def main():
    TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
    if not TOKEN:
        print("Error: TELEGRAM_BOT_TOKEN env variable not set.")
        return

    application = ApplicationBuilder().token(TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("startgame", start_game))
    application.add_handler(CommandHandler("join", join_game))
    application.add_handler(CommandHandler("quit", quit_game))
    application.add_handler(CommandHandler("status", status))
    application.add_handler(CommandHandler("scoreboard", scoreboard))
    application.add_handler(CallbackQueryHandler(button_handler))

    print("Bot started!")
    application.run_polling()


if __name__ == "__main__":
    main()
