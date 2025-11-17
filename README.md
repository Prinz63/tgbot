# 🎓 Paid Click Bot (School Project)

A simulated paid-to-click Telegram bot that uses points instead of real money.

Built with:
- Python `telegram-python-bot` v20+
- SQLite
- Flask (for uptime)

## ⚙️ Setup & Installation

### 1. Create Virtual Environment
bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate


### 2. Install Dependencies
pip install python-telegram-bot Flask

### 3. Set Token Environment Variable

Linux/macOS:
export BOT_TOKEN="your_token_here"

Windows:
set BOT_TOKEN="your_token_here"

On Replit – Go to Tools > Secrets ("Lock" symbol):
Key: BOT_TOKEN
Value: 8041634601:AAGyp4GcdKIQ8fgaTFhlezlLsX3DD1oORWc

### 4. Start the Bot!
python main.py


## 🧾 Features Implemented

- /start with referral handling
- Point-based system
- Ads opened with 15-second timers
- Referral stats via 👥 Referrals button
- Balance screen showing earned progress
- SQLite storage support

## ☁️ Keep Alive on Replit

The included Flask server ensures uptime.

## 📬 Contact Me
This was created as part of a school assignment. Do not run for commercial purposes.
