import os
import asyncio
import logging
import aiosqlite
from datetime import datetime, timedelta
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)

# -------------------------
# CONFIG
# -------------------------
TOKEN = os.environ.get("8041634601:AAHmkrLZmvWB1KrwT6rMZawwyG0EwMBsTls")
if not TOKEN:
    raise RuntimeError("BOT_TOKEN env var not set")

# Ads config
ADS = [
    {"id": "ad1", "title": "Ad 1", "url": "https://otieu.com/4/9224909"},
    {"id": "ad2", "title": "Ad 2", "url": "https://otieu.com/4/9224909"},
    {"id": "ad3", "title": "Ad 3", "url": "https://otieu.com/4/9224909"},
    {"id": "ad4", "title": "Ad 4", "url": "https://otieu.com/4/9224909"},
    {"id": "ad5", "title": "Ad 5", "url": "https://otieu.com/4/9224909"},
]
ADS_PER_CYCLE = 5
AD_AMOUNT_KOBO = 500            # ₦5.00 = 500 kobo
REFERRAL_PERCENT = 25           # 25%

DB_PATH = "bot.db"

# Anti-cheat / rate limits
AD_COOLDOWN_SECONDS = 5         # small cooldown to prevent double clicks
MAX_DAILY_EARNINGS_PER_USER = 50000 * 100  # example high cap in kobo if required

# -------------------------
# Logging
# -------------------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# -------------------------
# Utilities
# -------------------------
def kobo_to_naira_str(kobo: int) -> str:
    return f"₦{kobo/100:.2f}"

# -------------------------
# Database helpers
# -------------------------
async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            referral_code TEXT UNIQUE,
            referrer_id INTEGER,
            balance_kobo INTEGER DEFAULT 0,
            created_at TEXT
        )
        """)
        await db.execute("""
        CREATE TABLE IF NOT EXISTS earnings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            ad_id TEXT,
            amount_kobo INTEGER,
            referrer_bonus_kobo INTEGER,
            timestamp TEXT
        )
        """)
        await db.execute("""
        CREATE TABLE IF NOT EXISTS active_tasks (
            user_id INTEGER PRIMARY KEY,
            ad_id TEXT,
            started_at TEXT
        )
        """)
        await db.commit()

async def get_user(user_id):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT user_id, username, referral_code, referrer_id, balance_kobo FROM users WHERE user_id=?", (user_id,))
        row = await cur.fetchone()
        return row

async def create_user(user_id, username, referrer_code=None):
    async with aiosqlite.connect(DB_PATH) as db:
        # resolve referrer_code -> referrer_id
        referrer_id = None
        if referrer_code:
            cur = await db.execute("SELECT user_id FROM users WHERE referral_code=?", (referrer_code,))
            r = await cur.fetchone()
            if r:
                referrer_id = r[0]

        # create referral code (simple)
        referral_code = f"R{user_id}"  # deterministic code; can change
        now = datetime.utcnow().isoformat()
        await db.execute("""
            INSERT OR IGNORE INTO users (user_id, username, referral_code, referrer_id, created_at)
            VALUES (?, ?, ?, ?, ?)
        """, (user_id, username, referral_code, referrer_id, now))
        await db.commit()
        return referral_code

async def add_balance(user_id, amount_kobo):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET balance_kobo = balance_kobo + ? WHERE user_id=?", (amount_kobo, user_id))
        await db.commit()

async def record_earning(user_id, ad_id, amount_kobo, ref_bonus_kobo=0):
    async with aiosqlite.connect(DB_PATH) as db:
        now = datetime.utcnow().isoformat()
        await db.execute("""
            INSERT INTO earnings (user_id, ad_id, amount_kobo, referrer_bonus_kobo, timestamp)
            VALUES (?, ?, ?, ?, ?)
        """, (user_id, ad_id, amount_kobo, ref_bonus_kobo, now))
        await db.commit()

async def set_active_task(user_id, ad_id):
    async with aiosqlite.connect(DB_PATH) as db:
        now = datetime.utcnow().isoformat()
        await db.execute("INSERT OR REPLACE INTO active_tasks (user_id, ad_id, started_at) VALUES (?, ?, ?)", (user_id, ad_id, now))
        await db.commit()

async def clear_active_task(user_id):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM active_tasks WHERE user_id=?", (user_id,))
        await db.commit()

async def get_active_task(user_id):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT ad_id, started_at FROM active_tasks WHERE user_id=?", (user_id,))
        return await cur.fetchone()

async def get_referrer(user_id):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT referrer_id FROM users WHERE user_id=?", (user_id,))
        r = await cur.fetchone()
        return r[0] if r else None

# -------------------------
# Bot handlers
# -------------------------
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    user = update.effective_user
    args = context.args or []
    ref_code = args[0] if len(args) > 0 else None

    await create_user(user.id, user.username or user.full_name, ref_code)
    user_row = await get_user(user.id)
    referral_code = user_row[2]  # referral_code

    keyboard = [
        [InlineKeyboardButton("💰 Start Earning", callback_data="start_earning")],
        [InlineKeyboardButton("📈 Balance", callback_data="balance")],
        [InlineKeyboardButton("👥 Referrals", callback_data="referrals")],
        [InlineKeyboardButton("❓ Help", callback_data="help")],
    ]
    await message.reply_text(
        f"Welcome {user.first_name}!\nYour referral code: {referral_code}\nShare this link: t.me/{context.bot.username}?start={referral_code}",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = query.from_user.id

    if data == "balance":
        row = await get_user(user_id)
        bal_kobo = row[4] if row else 0
        await query.edit_message_text(f"📈 Your balance: {kobo_to_naira_str(bal_kobo)}")
        return

    if data == "referrals":
        # count referrals
        async with aiosqlite.connect(DB_PATH) as db:
            cur = await db.execute("SELECT COUNT(*) FROM users WHERE referrer_id = (SELECT user_id FROM users WHERE user_id=?)", (user_id,))
            count = (await cur.fetchone())[0]
        # earnings from referrals
        async with aiosqlite.connect(DB_PATH) as db:
            cur = await db.execute("SELECT SUM(referrer_bonus_kobo) FROM earnings WHERE referrer_bonus_kobo > 0 AND user_id IN (SELECT user_id FROM users WHERE referrer_id=?)", (user_id,))
            rr = await cur.fetchone()
            ref_earned = rr[0] if rr and rr[0] else 0
        await query.edit_message_text(f"👥 Referrals: {count}\nReferral earnings: {kobo_to_naira_str(ref_earned)}")
        return

    if data == "help":
        await query.edit_message_text("Help:\n• Click Start Earning → choose an ad → open the link and wait 15s in chat for credit.\n• Referrals give a percentage bonus to your referrer.")
        return

    if data == "start_earning":
        buttons = []
        for ad in ADS[:ADS_PER_CYCLE]:
            buttons.append([InlineKeyboardButton(f"📌 {ad['title']}", callback_data=f"ad|{ad['id']}")])
        await query.edit_message_text("Select an ad to view and earn:", reply_markup=InlineKeyboardMarkup(buttons))
        return

    if data.startswith("ad|"):
        # user selected an ad
        ad_id = data.split("|", 1)[1]
        ad = next((a for a in ADS if a["id"] == ad_id), None)
        if not ad:
            await query.edit_message_text("Ad not found.")
            return

        # Prevent double starting if active
        active = await get_active_task(user_id)
        if active:
            await query.edit_message_text("You already have an active ad task. Finish it first or wait for it to expire.")
            return

        # set active task
        await set_active_task(user_id, ad_id)

        # Provide external link and start the timer message
        sent = await query.edit_message_text(f"🔗 Open this link and stay for 15 seconds:\n{ad['url']}\n\n⏳ Countdown starting...")
        # start countdown message separately so we can update / delete
        countdown_msg = await context.bot.send_message(chat_id=user_id, text="⏳ Viewing ad... 15s remaining")

        # countdown loop - update every 5 seconds to reduce edits
        remaining = 15
        try:
            while remaining > 0:
                await asyncio.sleep(1)
                remaining -= 1
                if remaining in (10, 5, 3, 2, 1):
                    # edit every few seconds
                    try:
                        await context.bot.edit_message_text(chat_id=user_id, message_id=countdown_msg.message_id,
                                                           text=f"⏳ Viewing ad... {remaining}s remaining")
                    except Exception:
                        # ignore edit errors (message deleted by user maybe)
                        pass

            # finished timer — credit user
            await context.bot.delete_message(chat_id=user_id, message_id=countdown_msg.message_id)
            # credit main user
            await add_balance(user_id, AD_AMOUNT_KOBO)
            # calculate referral bonus
            ref_id = await get_referrer(user_id)
            ref_bonus_kobo = 0
            if ref_id:
                ref_bonus_kobo = round(AD_AMOUNT_KOBO * REFERRAL_PERCENT / 100)
                await add_balance(ref_id, ref_bonus_kobo)
            await record_earning(user_id, ad_id, AD_AMOUNT_KOBO, ref_bonus_kobo)

            # clear active task
            await clear_active_task(user_id)

            # send success messages
            await context.bot.send_message(chat_id=user_id, text=f"🎉 {kobo_to_naira_str(AD_AMOUNT_KOBO)} has been added to your balance!")
            if ref_id and ref_bonus_kobo > 0:
                try:
                    await context.bot.send_message(chat_id=ref_id, text=f"💸 You earned {kobo_to_naira_str(ref_bonus_kobo)} as a {REFERRAL_PERCENT}% referral bonus!")
                except Exception:
                    # referrer might have blocked bot / unavailable
                    pass

        except asyncio.CancelledError:
            # if something cancels, clear
            await clear_active_task(user_id)
            raise
        except Exception as e:
            logger.exception("Error during ad timer")
            await clear_active_task(user_id)
            try:
                await context.bot.send_message(chat_id=user_id, text="⚠️ Something went wrong during the ad. Please try again.")
            except Exception:
                pass

# Quick command to show full menu on text triggers
async def menu_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("💰 Start Earning", callback_data="start_earning")],
        [InlineKeyboardButton("📈 Balance", callback_data="balance")],
        [InlineKeyboardButton("👥 Referrals", callback_data="referrals")],
        [InlineKeyboardButton("❓ Help", callback_data="help")],
    ]
    await update.message.reply_text("Main menu:", reply_markup=InlineKeyboardMarkup(keyboard))

# -------------------------
# Startup
# -------------------------
async def startup(app):
    await init_db()
    logger.info("Database initialized.")

def main():
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("menu", menu_command))
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.post_init(startup)

    logger.info("Bot starting...")
    app.run_polling()

if __name__ == "__main__":
    main()
