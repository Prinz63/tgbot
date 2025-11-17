import sqlite3
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes
import asyncio
import random
import string
import uuid  # For generating unique IDs

# ----------------------------
# CONFIGURABLE SETTINGS HERE
# ----------------------------
BOT_TOKEN = "8041634601:AAHmkrLZmvWB1KrwT6rMZawwyG0EwMBsTls"

# List of required Telegram channels user must join
CHANNEL_ID_USERNAME_MAP = {
    "@ptcrealchannel": "-1001183165077",
    # "@another_channel": "-100123456789",
}

ADMIN_USER_IDS = [1234567890, 9876543210]  # Replace with real admin IDs
WITHDRAWAL_MINIMUM = 100  # Amount in NGN
CURRENCY_SYMBOL = "₦"

# ----------------------------
# LOGGING
# ----------------------------
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# ----------------------------
# DATABASE SETUP
# ----------------------------
conn = sqlite3.connect('ptc_bot.db', check_same_thread=False)
cursor = conn.cursor()

cursor.executescript("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    username TEXT,
    balance INTEGER DEFAULT 0,
    referral_code TEXT UNIQUE,
    referred_by TEXT,
    joined_channels BOOLEAN DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS referrals (
    referrer_code TEXT,
    referred_user_id INTEGER,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS ads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT,
    link TEXT
);

CREATE TABLE IF NOT EXISTS withdrawals (
    request_id TEXT PRIMARY KEY,
    user_id INTEGER,
    amount REAL,
    status TEXT CHECK(status IN ('pending', 'approved')),
    bank_details TEXT,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
);
""")

# Pre-populate test ads if none exist
cursor.execute("SELECT COUNT(*) FROM ads")
if cursor.fetchone()[0] == 0:
    for i in range(1, 6):
        cursor.execute("INSERT INTO ads (title, link) VALUES (?, ?)",
                       (f"Ad Offer #{i}", "https://otieu.com/4/9224909"))
    conn.commit()
conn.close()


# ----------------------------
# HELPER FUNCTIONS
# ----------------------------

def get_db():
    return sqlite3.connect('ptc_bot.db')


def generate_referral_code(length=6):
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=length))


def register_user(user_id, username, referred_by=None):
    db = get_db()
    cur = db.cursor()
    code = generate_referral_code()
    try:
        cur.execute("""
            INSERT INTO users (user_id, username, referral_code, referred_by) 
            VALUES (?, ?, ?, ?)
        """, (user_id, username, code, referred_by))

        # Add referral tracking
        if referred_by:
            cur.execute("INSERT INTO referrals (referrer_code, referred_user_id) VALUES (?, ?)",
                        (referred_by, user_id))

        db.commit()
        return code
    except sqlite3.IntegrityError:
        return False  # Already registered
    finally:
        db.close()


async def force_join_channels(update: Update) -> bool:
    """Returns True if user passed channel checks."""
    user_id = update.effective_user.id
    db = get_db()
    cur = db.cursor()

    # Fetch existing status
    cur.execute("SELECT joined_channels FROM users WHERE user_id=?", (user_id,))
    row = cur.fetchone()

    if row and row[0]:  # Already checked?
        db.close()
        return True

    # Perform checks for all defined channels
    failed_joins = []

    for username, chat_id in CHANNEL_ID_USERNAME_MAP.items():
        try:
            member = await update.get_bot().get_chat_member(chat_id, user_id)
            if member.status not in ['member', 'administrator', 'creator']:
                failed_joins.append(username)
        except Exception:
            failed_joins.append(username)

    if not failed_joins:
        cur.execute("UPDATE users SET joined_channels=TRUE WHERE user_id=?", (user_id,))
        db.commit()
        db.close()
        return True

    keyboard = [[InlineKeyboardButton("✅ Joined Channels?", callback_data="check_subscription")]]
    await update.message.reply_text(
        f"You need to join the following channels to proceed:\n" +
        '\n👉 @'.join([''] + list(map(str.strip, CHANNEL_ID_USERNAME_MAP.keys()))),
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    db.close()
    return False


# ----------------------------
# HANDLERS
# ----------------------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    db = get_db()
    cur = db.cursor()

    referred_by = None
    if context.args:
        referee_code = context.args[0]
        cur.execute("SELECT referral_code FROM users WHERE referral_code=?", (referee_code,))
        result = cur.fetchone()
        if result:
            referred_by = referee_code

    register_status = register_user(user.id, user.username, referred_by=referred_by)
    db.close()

    success = await force_join_channels(update)
    if success:
        await show_home_menu(update)
    else:
        pass


async def process_callback_query(update: Update, context):
    query = update.callback_query
    await query.answer()
    action = query.data.split('|')

    if action[0] == 'menu':
        await show_home_menu(query)

    elif action[0] == 'balance':
        await show_balance(query)

    elif action[0] == 'ads':
        await show_ads_list(query)

    elif action[0].startswith('view_ad'):
        ad_index = int(action[1]) - 1
        cursor.execute("SELECT link FROM ads LIMIT 1 OFFSET ?", (ad_index,))
        ad_link = cursor.fetchone()[0]
        await initiate_ad_task(context, query.from_user.id, ad_link, ad_index)

    elif action[0] == 'referrals':
        await view_referral_stats(query)

    elif action[0] == 'withdraw':
        await initiate_withdraw_request(query)

    elif action[0] == 'submit_withdraw':
        await submit_withdraw_details(query)

    elif action[0] == 'admin':
        user_id = query.from_user.id
        if user_id not in ADMIN_USER_IDS:
            await query.answer("Unauthorized access.", show_alert=True)
            return
        await enter_admin_panel(query)

    elif action[0] == 'approve_withdrawals':
        await display_pending_withdrawals(query)

    elif action[0] == 'approve_single':
        request_id = action[1]
        user_id = int(action[2])
        await approve_specific_withdrawal(query, request_id, user_id)

    elif action[0] == 'check_subscription':
        success = await force_join_channels(update)
        if success:
            await query.edit_message_text("✅ You've joined all required channels!")
            await show_home_menu(query)


async def show_home_menu(update_or_query):
    text = """
🔹 Welcome To Premium PTC Portal 🔸

Earn real cash daily watching sponsored ads. Participate safely and withdraw anytime!

"""

    buttons = [
        [InlineKeyboardButton("📈 My Balance", callback_data="balance")],
        [InlineKeyboardButton("💰 View Ads Today", callback_data="ads")],
        [InlineKeyboardButton("🤝 Referral Dashboard", callback_data="referrals")],
        [InlineKeyboardButton("📤 Request Withdrawal", callback_data="withdraw")],
        [InlineKeyboardButton("🛠 Admin Access", callback_data="admin")]
    ]

    markup = InlineKeyboardMarkup(buttons)

    if isinstance(update_or_query, CallbackQuery):
        await update_or_query.edit_message_text(text=text, reply_markup=markup)
    else:
        await update_or_query.message.reply_text(text=text, reply_markup=markup)


async def show_balance(update):
    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT balance FROM users WHERE user_id=?", (update.from_user.id,))
    row = cur.fetchone()
    db.close()

    balance = row[0] if row else 0
    msg = f"{CURRENCY_SYMBOL}{balance}"

    buttons = [[InlineKeyboardButton("← Back", callback_data="menu")]]

    await update.edit_message_text(text=f"💳 Current Balance: {msg}", reply_markup=InlineKeyboardMarkup(buttons))


# ... truncated snippet continues below
