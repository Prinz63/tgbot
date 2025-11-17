import sqlite3
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes
import asyncio
import random
import string

# -----------------------------
# Logging
# -----------------------------
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)

# -----------------------------
# Database setup
# -----------------------------
conn = sqlite3.connect('bot.db', check_same_thread=False)
cursor = conn.cursor()

# Create tables
cursor.execute('''
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    username TEXT,
    referral_code TEXT,
    balance INTEGER DEFAULT 0,
    referrer TEXT
)
''')
conn.commit()

# -----------------------------
# Helpers
# -----------------------------
def generate_referral_code(length=6):
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=length))

def add_user(user_id, username, referrer=None):
    cursor.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
    if cursor.fetchone() is None:
        code = generate_referral_code()
        cursor.execute(
            "INSERT INTO users (user_id, username, referral_code, referrer) VALUES (?, ?, ?, ?)",
            (user_id, username, code, referrer)
        )
        conn.commit()
        return code
    return None

def get_balance(user_id):
    cursor.execute("SELECT balance FROM users WHERE user_id=?", (user_id,))
    result = cursor.fetchone()
    return result[0] if result else 0

def add_balance(user_id, amount):
    cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id=?", (amount, user_id))
    conn.commit()

# -----------------------------
# Commands
# -----------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    username = update.effective_user.username or "User"
    referrer = None

    # Check if user started with a referral
    if context.args:
        ref_code = context.args[0]
        cursor.execute("SELECT user_id FROM users WHERE referral_code=?", (ref_code,))
        ref = cursor.fetchone()
        if ref:
            referrer = ref_code
            # Reward referrer
            add_balance(ref[0], 20)

    code = add_user(user_id, username, referrer)
    balance = get_balance(user_id)

    keyboard = [
        [InlineKeyboardButton("💰 Start Earning", callback_data="start_earning")],
        [InlineKeyboardButton("📊 Balance", callback_data="balance")],
        [InlineKeyboardButton("🏆 Referrals", callback_data="referrals")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        f"Welcome {username}! Your referral code is: {code}\nYour balance: ₦{balance}", 
        reply_markup=reply_markup
    )

# -----------------------------
# Callback Query
# -----------------------------
ads = [
    {"title": "Ad 1", "url": "https://otieu.com/4/9224909"},
    {"title": "Ad 2", "url": "https://otieu.com/4/9224909"},
    {"title": "Ad 3", "url": "https://otieu.com/4/9224909"},
    {"title": "Ad 4", "url": "https://otieu.com/4/9224909"},
    {"title": "Ad 5", "url": "https://otieu.com/4/9224909"},
]

async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    if query.data == "balance":
        balance = get_balance(user_id)
        await query.edit_message_text(f"💰 Your balance: ₦{balance}")
    
    elif query.data == "referrals":
        cursor.execute("SELECT COUNT(*) FROM users WHERE referrer=(SELECT referral_code FROM users WHERE user_id=?)", (user_id,))
        count = cursor.fetchone()[0]
        await query.edit_message_text(f"🏆 Your referrals: {count}\nEarned: ₦{count*20}")

    elif query.data == "start_earning":
        keyboard = []
        for ad in ads:
            keyboard.append([InlineKeyboardButton(f"📌 {ad['title']}", callback_data=f"ad|{ad['url']}")])
        await query.edit_message_text("Select an ad to view and earn:", reply_markup=InlineKeyboardMarkup(keyboard))

    elif query.data.startswith("ad|"):
        ad_url = query.data.split("|")[1]
        await query.edit_message_text(f"🔗 Open this link and stay 15s: {ad_url}\n⏳ Timer starting...")
        await start_ad_timer(context, user_id)

# -----------------------------
# Timer for ad view
# -----------------------------
async def start_ad_timer(context, user_id):
    timer_msg = await context.bot.send_message(chat_id=user_id, text="⏳ Viewing ad... 15s remaining")
    await asyncio.sleep(15)
    await timer_msg.delete()
    add_balance(user_id, 5)
    await context.bot.send_message(chat_id=user_id, text="💸 ₦5 has been added to your balance!")

# -----------------------------
# Run Bot
# -----------------------------
if __name__ == "__main__":
    TOKEN = "8041634601:AAHmkrLZmvWB1KrwT6rMZawwyG0EwMBsTls"
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button))

    print("Bot is running...")
    app.run_polling()
