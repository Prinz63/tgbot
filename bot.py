import os
import sqlite3
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)

# ========================
# DATABASE INITIALIZATION
# ========================

DB_NAME = "bot.db"

def init_db():
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                points INTEGER DEFAULT 0,
                referrals INTEGER DEFAULT 0
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                user_id INTEGER,
                ad_id TEXT,
                completed BOOLEAN
            )
        """)
        conn.commit()

def add_user(user_id):
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,))
        conn.commit()

def get_user(user_id):
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
        return cursor.fetchone()

def update_points(user_id, delta):
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET points = points + ? WHERE user_id=?", (delta, user_id))
        conn.commit()

def increment_referrals(user_id):
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET referrals = referrals + 1 WHERE user_id=?", (user_id,))
        conn.commit()

# ========================
# COMMAND HANDLERS
# ========================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    referral_id = None

    add_user(user_id)

    # Check referral
    args = context.args
    if len(args) > 0 and args[0].isdigit():
        referral_id = int(args[0])
        if referral_id != user_id:
            user_data = get_user(referral_id)
            if user_data:
                update_points(referral_id, 20)
                increment_referrals(referral_id)

    await send_main_menu(update)

async def send_main_menu(update: Update):
    keyboard = [
        [InlineKeyboardButton("📈 Balance", callback_data="balance")],
        [InlineKeyboardButton("👥 Referrals", callback_data="referrals")],
        [InlineKeyboardButton("💰 Start Earning", callback_data="start_earning")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "👋 Welcome! Let's boost your points!\n\nClick below to get started:",
        reply_markup=reply_markup
    )

async def handle_menu_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "balance":
        await show_balance(query)
    elif query.data == "referrals":
        await show_referrals(query)
    elif query.data.startswith("start_earning"):
        await start_earning(query)
    elif query.data.startswith("ad_"):
        await open_ad(query)
    elif query.data.startswith("done_"):
        await close_task_before_finish(query)

# ========================
# BALANCE SCREEN
# ========================

async def show_balance(query):
    user_id = query.from_user.id
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT points FROM users WHERE user_id=?", (user_id,))
        user = cursor.fetchone()
        if not user:
            await query.edit_message_text(text="⚠️ User not found.")
            return

        points = user[0]
        cursor.execute("SELECT COUNT(*) FROM tasks WHERE user_id=? AND completed=1", (user_id,))
        count_ads = cursor.fetchone()[0]

    msg = f"""📊 Your Stats:\n\nPoints: {points}\nAds Completed: {count_ads}"""
    await query.edit_message_text(text=msg, reply_markup=back_to_main())

# ========================
# REFERRAL INFO
# ========================

async def show_referrals(query):
    user_id = query.from_user.id
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT referrals FROM users WHERE user_id=?", (user_id,))
        user = cursor.fetchone()
        if not user:
            await query.edit_message_text(text="⚠️ User not found.")
            return

        total_referrals = user[0]
        total_bonus = total_referrals * 20

    msg = f"""👥 Referrals Info:\n\nTotal Referrals: {total_referrals}\nBonus Points Earned: {total_bonus}"""
    await query.edit_message_text(text=msg, reply_markup=back_to_main())

# ========================
# START EARNING SYSTEM
# ========================

ADS = [f"https://otieu.com/4/922490{i}" for i in range(9)]

async def start_earning(query):
    btns = [[InlineKeyboardButton(f"Ad {i+1}", url=link)] +
            [InlineKeyboardButton("✅ I'm Done", callback_data=f"done_{i}_{query.from_user.id}")]
             for i, link in enumerate(ADS)]
    
    keyboard = btns[:5]  # show only first 5 ads
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(text="Click an Ad below:", reply_markup=reply_markup)

async def open_ad(query):
    ad_index = int(query.data.split('_')[1])
    url = ADS[ad_index]

    keyboard = [[InlineKeyboardButton("✅ I'm Done", callback_data=f'done_{ad_index}_{query.from_user.id}')]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    msg = await query.message.reply_text("🕒 Starting Timer...\n⏱ Counting down...")
    
    for sec in range(15, 0, -1):
        try:
            await msg.edit_text(f"⏳ Timer Remaining: `{sec}s`\nDon't leave yet!", parse_mode='Markdown')
        except:
            break
        await asyncio.sleep(1)

    try:
        await msg.delete()
    except:
        pass

    update_points(query.from_user.id, 5)

    await query.message.reply_text("🎉 5 points have been added to your balance!")

def back_to_main():
    kb = [[InlineKeyboardButton("⬅️ Back to Menu", callback_data="main_menu")]]
    return InlineKeyboardMarkup(kb)

async def close_task_before_finish(query):
    try:
        await query.message.reply_text("⚠️ You closed the task before the required time. No points added.")
        await query.edit_message_text(text=query.message.text + "\n\n(Timed Task Cancelled)")
    except:
        pass

# ========================
# REPLIT SERVER KEEP-ALIVE
# ========================
from flask import Flask
from threading import Thread

app = Flask("")

@app.route("/")
def home():
    return "✅ Bot is running!"

def run():
    app.run(host="0.0.0.0", port=8080)

if __name__ == "__main__":
    init_db()
    print("[+] Initializing Telegram Bot...")
    TOKEN = os.environ.get('BOT_TOKEN')

    if not TOKEN:
        raise ValueError("⚠️ Please set BOT_TOKEN environment variable.")

    application = ApplicationBuilder().token(TOKEN).build()

    # Command Handlers
    application.add_handler(CommandHandler("start", start))

    # Callback Query Handler
    application.add_handler(CallbackQueryHandler(handle_menu_button))

    # Web Server Thread for Replit
    thread = Thread(target=run)
    thread.start()

    # Polling Mode
    print("[+] Starting Polling...")
    application.run_polling()
