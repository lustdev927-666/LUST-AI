import os
import logging
import sqlite3
from collections import defaultdict
from time import time

from openai import OpenAI
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ChatAction
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

if not OPENAI_API_KEY:
    raise RuntimeError("OPENAI_API_KEY manquant")

if not TELEGRAM_BOT_TOKEN:
    raise RuntimeError("TELEGRAM_BOT_TOKEN manquant")

client = OpenAI(api_key=OPENAI_API_KEY)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | LUST AI | %(levelname)s | %(message)s"
)
logger = logging.getLogger("LUST_AI")

PERSONNALITES = {
    "serieux": ("🎓 Sérieux", "Tu es un assistant professionnel, précis et structuré."),
    "decontracte": ("😎 Décontracté", "Tu réponds comme un ami cool et naturel."),
    "poete": ("🌹 Poète", "Tu écris avec des métaphores et un style élégant."),
    "humoriste": ("😂 Humoriste", "Tu ajoutes un humour intelligent quand c'est pertinent."),
    "philosophe": ("🧠 Philosophe", "Tu analyses les idées avec profondeur."),
    "coach": ("💪 Coach", "Tu motives avec énergie et discipline."),
    "dark": ("🌑 Dark LUST", "Style mystérieux, intense et élégant."),
    "genius": ("🧬 Genius", "Tu expliques clairement même les sujets complexes."),
}

MAX_HISTORY = 10
cooldowns = {}
user_style = defaultdict(lambda: "serieux")
user_history = defaultdict(list)
user_stats = defaultdict(lambda: {"messages": 0})

db = sqlite3.connect("lust_ai.db", check_same_thread=False)
db.execute("""
CREATE TABLE IF NOT EXISTS styles (
    user_id INTEGER PRIMARY KEY,
    style TEXT
)
""")
db.commit()

def save_style(user_id, style):
    db.execute(
        "INSERT OR REPLACE INTO styles(user_id, style) VALUES (?, ?)",
        (user_id, style)
    )
    db.commit()

def load_style(user_id):
    cur = db.execute(
        "SELECT style FROM styles WHERE user_id=?",
        (user_id,)
    )
    row = cur.fetchone()
    return row[0] if row else "serieux"

def add_history(uid, role, content):
    user_history[uid].append({"role": role, "content": content})
    user_history[uid] = user_history[uid][-MAX_HISTORY:]

def build_menu():
    return [
        [InlineKeyboardButton(v[0], callback_data=f"style_{k}")]
        for k, v in PERSONNALITES.items()
    ]

async def anti_spam(uid):
    now = time()
    if uid in cooldowns and now - cooldowns[uid] < 2:
        return False
    cooldowns[uid] = now
    return True

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🚀 LUST AI\n\nChoisis une personnalité :",
        reply_markup=InlineKeyboardMarkup(build_menu())
    )

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "/start\n/help\n/style\n/me\n/reset\n/stats\n/ping"
    )

async def ping(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🏓 LUST AI ONLINE")

async def me(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    style = user_style[uid]
    await update.message.reply_text(
        f"🎭 Style actuel : {PERSONNALITES[style][0]}"
    )

async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    user_history[uid].clear()
    await update.message.reply_text("🧹 Mémoire réinitialisée")

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    await update.message.reply_text(
        f"📊 Messages : {user_stats[uid]['messages']}"
    )

async def style_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🎭 Choisis un style",
        reply_markup=InlineKeyboardMarkup(build_menu())
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    style_key = query.data.replace("style_", "")
    user_style[query.from_user.id] = style_key
    save_style(query.from_user.id, style_key)

    await query.edit_message_text(
        f"✅ Style activé : {PERSONNALITES[style_key][0]}"
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    text = update.message.text

    if not await anti_spam(uid):
        await update.message.reply_text("⏳ Attends un instant.")
        return

    user_stats[uid]["messages"] += 1

    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id,
        action=ChatAction.TYPING
    )

    try:
        style = user_style[uid]

        messages = [
            {
                "role": "system",
                "content": PERSONNALITES[style][1]
            },
            *user_history[uid],
            {
                "role": "user",
                "content": text
            }
        ]

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            temperature=0.9
        )

        answer = response.choices[0].message.content

        add_history(uid, "user", text)
        add_history(uid, "assistant", answer)

        await update.message.reply_text(
            f"{answer}\n\n— LUST AI ⚡"
        )

    except Exception as e:
        logger.exception(e)
        await update.message.reply_text(
            "❌ Erreur IA temporaire."
        )

async def post_init(app):
    logger.info("🔥 LUST AI READY")

def main():
    app = (
        Application.builder()
        .token(TELEGRAM_BOT_TOKEN)
        .post_init(post_init)
        .build()
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("ping", ping))
    app.add_handler(CommandHandler("style", style_cmd))
    app.add_handler(CommandHandler("me", me))
    app.add_handler(CommandHandler("reset", reset))
    app.add_handler(CommandHandler("stats", stats))

    app.add_handler(CallbackQueryHandler(button_handler))

    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message)
    )

    app.run_polling()

if __name__ == "__main__":
    for uid in list(user_style.keys()):
        user_style[uid] = load_style(uid)
    main()
