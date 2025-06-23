import random
import asyncio

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)
from telegram.constants import ChatType

async def safe_reply(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str, **kwargs):
    if update.message:
        await update.message.reply_text(text, **kwargs)
    elif update.effective_chat:
        await context.bot.send_message(update.effective_chat.id, text, **kwargs)

# Questions by difficulty level
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
            InlineKeyboardButton("🔥 Dare", callback_data="dare"),
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    context.chat_data["active_user"] = user_id

    await context.bot.send_message(
        chat_id,
        f"➡️ It's {name}'s turn! Choose: Truth or Dare?",
        reply_markup=reply_markup,
    )

    # Set a timeout task to auto-skip if no choice is made
    context.chat_data["turn_task"] = context.application.create_task(turn_timeout(context, chat_id, user_id))


async def turn_timeout(context: ContextTypes.DEFAULT_TYPE, chat_id, user_id):
    await asyncio.sleep(TURN_TIMEOUT)

    # Check if still waiting for the same user
    if context.chat_data.get("active_user") == user_id:
        await context.bot.send_message(chat_id, f"⏰ Time's up for <a href='tg://user?id={user_id}'>your turn</a>! Skipping turn.", parse_mode="HTML")
        # Advance turn
        context.chat_data["current_turn"] += 1
        context.chat_data["active_user"] = None
        await ask_truth_or_dare(context, chat_id)


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = update.effective_user
    chat_id = update.effective_chat.id
    await query.answer()

    active_user = context.chat_data.get("active_user")
    if user.id != active_user:
        await query.edit_message_text("❌ It's not your turn!")
        return

    choice = query.data  # "truth" or "dare"
    difficulty = context.chat_data.get("difficulty", "medium")

    # Cancel timeout task if running
    turn_task = context.chat_data.get("turn_task")
    if turn_task:
        turn_task.cancel()

    # Pick question or dare randomly
    if choice == "truth":
        question = random.choice(TRUTHS[difficulty])
        await query.edit_message_text(f"❓ Truth: {question}")
    else:
        question = random.choice(DARES[difficulty])
        await query.edit_message_text(f"🔥 Dare: {question}")

    # After 30 seconds, ask for done or pass buttons
    keyboard = [
        [
            InlineKeyboardButton("✅ Done", callback_data="done"),
            InlineKeyboardButton("⏭️ Pass", callback_data="pass"),
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await context.bot.send_message(chat_id, "Did you complete the task?", reply_markup=reply_markup)

    # Store current challenge for checking
    context.chat_data["current_challenge"] = {
        "user_id": user.id,
        "choice": choice,
    }


async def challenge_response_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = update.effective_user
    chat_id = update.effective_chat.id
    await query.answer()

    current_challenge = context.chat_data.get("current_challenge")
    active_user = context.chat_data.get("active_user")

    if current_challenge is None or user.id != current_challenge.get("user_id"):
        await query.edit_message_text("❌ This is not your challenge.")
        return

    if query.data == "done":
        # Increase score for completing challenge
        scores = context.chat_data.get("scores", {})
        scores[user.id] = scores.get(user.id, 0) + 1
        context.chat_data["scores"] = scores

        await query.edit_message_text("🎉 Challenge completed! +1 point.")
    else:
        # Eliminate player for passing
        eliminated = context.chat_data.get("eliminated", set())
        eliminated.add(user.id)
        context.chat_data["eliminated"] = eliminated
        await query.edit_message_text("🚫 You passed and are eliminated from the game.")

    # Move to next turn
    context.chat_data["current_turn"] += 1
    context.chat_data["active_user"] = None
    context.chat_data["current_challenge"] = None

    await ask_truth_or_dare(context, chat_id)


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    in_game = context.chat_data.get("in_game", False)
    if not in_game:
        await update.message.reply_text("❌ No game in progress.")
        return

    players = context.chat_data.get("players", [])
    eliminated = context.chat_data.get("eliminated", set())
    scores = context.chat_data.get("scores", {})
    round_num = context.chat_data.get("round", 1)
    current_turn = context.chat_data.get("current_turn", 0)

    alive_players = [p for p in players if p[0] not in eliminated]

    if current_turn < len(players):
        active_player_id, active_player_name = players[current_turn]
    else:
        active_player_id = None
        active_player_name = None

    status_text = (
        f"🎲 *Game Status*\n"
        f"Round: {round_num}/{TOTAL_ROUNDS}\n"
        f"Players: {', '.join([p[1] for p in alive_players])}\n"
        f"Eliminated: {', '.join([p[1] for p in players if p[0] in eliminated]) or 'None'}\n"
        f"Current Turn: {active_player_name if active_player_name else 'N/A'}\n\n"
        f"Scores:\n"
    )

    for uid, name in players:
        score = scores.get(uid, 0)
        eliminated_mark = " (eliminated)" if uid in eliminated else ""
        status_text += f"- {name}: {score} points{eliminated_mark}\n"

    await update.message.reply_text(status_text, parse_mode="Markdown")


async def scoreboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    scores = context.chat_data.get("scores", {})
    players = context.chat_data.get("players", [])
    eliminated = context.chat_data.get("eliminated", set())

    if not scores or not players:
        await update.message.reply_text("❌ No game in progress.")
        return

    sorted_scores = sorted(
        ((name, scores.get(uid, 0), uid) for uid, name in players),
        key=lambda x: x[1],
        reverse=True,
    )

    text = "📊 *Scoreboard:*\n"
    for name, score, uid in sorted_scores:
        elim_mark = " (eliminated)" if uid in eliminated else ""
        text += f"{name}: {score} points{elim_mark}\n"

    await update.message.reply_text(text, parse_mode="Markdown")


def get_handlers():
    return [
        CommandHandler("start", start),
        CommandHandler("startgame", start_game),
        CommandHandler("join", join_game),
        CommandHandler("quit", quit_game),
        CommandHandler("status", status),
        CommandHandler("scoreboard", scoreboard),
        CallbackQueryHandler(button_handler, pattern="^(truth|dare)$"),
        CallbackQueryHandler(challenge_response_handler, pattern="^(done|pass)$"),
    ]
