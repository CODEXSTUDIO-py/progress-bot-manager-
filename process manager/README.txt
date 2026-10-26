PROCESS MANAGER BOT — QUICK SETUP
================================

1. Install Python 3.9+: https://www.python.org/downloads/
   On Windows, enable "Add Python to PATH".

2. Copy .env.example and rename the copy to .env.

3. Open .env and set your values:
   BOT_TOKEN=YOUR_TOKEN_FROM_BOTFATHER
   ADMIN_ID=YOUR_TELEGRAM_USER_ID

4. Open Command Prompt in this folder and install the libraries:
   py -m pip install -r requirements.txt

5. Start the bot:
   py bot.py

Open your bot in Telegram and send /start.
Keep the terminal open while the bot is running; press Ctrl+C to stop it.

COMMANDS
--------
/start — Open the menu
/help — Show help
/status — Show CPU, RAM, disk usage, and process count
/topcpu — Top processes by CPU usage
/topram — Top processes by RAM usage
/search chrome — Search for processes containing "chrome"
/kill 1234 — Request to terminate a process by PID

SECURITY
--------
Get your token from @BotFather. Keep .env private and never share your token.
If it leaks, revoke it with @BotFather and update BOT_TOKEN in .env.
Only terminate processes you recognize; unsaved work may be lost.
