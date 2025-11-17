import os
import sqlite3
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)
from flask import Flask, request

# ----------------------------
# CONFIGURATIONS
# ----------------------------
TOKEN = os.getenv("8041634601:AAHmkrLZmvWB1KrwT6rMZawwyG0EwMBsTls")
if not TOKEN:
    raise ValueError("🚨 Please set BOT_TOKEN in Railway environment variables.")

PORT = int(os.environ.get("PORT", 8080))
WEBHOOK_PATH = f"/{TOKEN}"
WEBHOOK_URL = f"https://{os.environ['RAILWAY_STATIC_URL']}{WEBHOOK_PATH}" \
    if 'RAILWAY_STATIC_URL' in os.environ else f"https://yourdomain.ngrok.io{WEBHOOK_PATH}"

# ----------------------------
# DATABASE SETUP
# ----------------------------
conn = sqlite3.connect('bot.db', check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        balance INTEGER DEFAULT 0,
        referral_code TEXT UNIQUE,
        referred_by TEXT,
        joined_channels BOOLEAN DEFAULT FALSE
    );
""")
conn.commit()
conn.close()

# ----------------------------
# INITIALIZATION
# ----------------------------
logging.basicConfig(level=logging.INFO)

# ----------------------------
# FLASK APP FOR HEALTH CHECK
# ----------------------------
app = Flask(__name__)

@app.route("/", methods=["GET"])
def index():
    return {"status": "✅ Bot is running on Railway!"}, 200

@app.route(WEBHOOK_PATH, methods=["POST"])
def webhook():
    json_str = request.get_data().decode("utf-8")
    update = Update.de_json(json_str, application.bot)
    application.process_update(update)
    return {"status": "ok"}

# ----------------------------
# TELEGRAM BOT LOGIC
# ----------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    await update.message.reply_text("👋 Hello and welcome to the bot!")

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(text="✅ Action completed.")

# ----------------------------
# APP STARTUP WITH WEBHOOK
# ----------------------------
if __name__ == "__main__":
    global application
    application = ApplicationBuilder().token(TOKEN).build()

    # Register handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(button_handler))

    # Start webhook
    application.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        url_path=WEBHOOK_PATH,
        webhook_url=WEBHOOK_URL
    )

    # Start Flask app on separate thread
    from threading import Thread
    Thread(target=lambda: app.run(host="0.0.0.0", port=PORT, debug=False, use_reloader=False)).start()
