import os
import time
import threading

import psutil
import telebot
from telebot import types
from dotenv import load_dotenv

# Load configuration from the .env file.
load_dotenv()

TOKEN = os.getenv("BOT_TOKEN", "").strip()
ADMIN_ID_STR = os.getenv("ADMIN_ID", "").strip()
ADMIN_ID = int(ADMIN_ID_STR) if ADMIN_ID_STR.isdigit() else None

if not TOKEN:
    raise RuntimeError(
        "BOT_TOKEN is missing. Add your Telegram bot token to the .env file."
    )

if ADMIN_ID is None:
    raise RuntimeError(
        "ADMIN_ID is missing or invalid. Add your numeric Telegram user ID to the .env file."
    )

bot = telebot.TeleBot(TOKEN)

# Stores users who are currently expected to enter a process name.
user_states = {}


def is_authorized(user_id):
    """Return True only for the configured administrator."""
    return user_id == ADMIN_ID


def get_main_keyboard():
    """Create the main menu keyboard."""
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row("📊 System status", "🔍 Search process")
    markup.row("🔥 Top CPU", "💾 Top RAM")
    return markup


def get_processes_info():
    """Collect process CPU and RAM usage."""
    # Prime CPU counters before reading them.
    for process in psutil.process_iter(["pid"]):
        try:
            process.cpu_percent()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

    time.sleep(0.2)
    processes = []

    for process in psutil.process_iter(["pid", "name", "memory_percent"]):
        try:
            cpu = process.cpu_percent(interval=None)
            memory = process.info["memory_percent"] or 0.0
            processes.append({
                "pid": process.info["pid"],
                "name": process.info["name"] or "Unknown",
                "cpu": cpu,
                "mem": memory,
            })
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

    return processes


@bot.message_handler(commands=["start"])
def send_welcome(message):
    if not is_authorized(message.from_user.id):
        bot.send_message(message.chat.id, "❌ You are not authorized to use this bot.")
        return

    welcome_text = (
        "Hello! I am Process Manager.\n\n"
        "I can help you monitor system processes, check system load, "
        "and terminate unresponsive applications.\n\n"
        "Choose an action from the menu or use /help."
    )
    bot.send_message(message.chat.id, welcome_text, reply_markup=get_main_keyboard())


@bot.message_handler(commands=["help"])
def send_help(message):
    if not is_authorized(message.from_user.id):
        return

    help_text = (
        "📖 Command help:\n\n"
        "/start - Restart the bot and open the menu\n"
        "/help - Show this help message\n"
        "/status - Show system load (CPU, RAM, disk)\n"
        "/topcpu - Show the top processes by CPU usage\n"
        "/topram - Show the top processes by RAM usage\n"
        "/search <name> - Search for a process by name\n"
        "/kill <pid> - Request to terminate a process by PID"
    )
    bot.send_message(message.chat.id, help_text)


@bot.message_handler(commands=["status"])
def send_status(message):
    if not is_authorized(message.from_user.id):
        return

    try:
        cpu_usage = psutil.cpu_percent(interval=0.5)
        ram = psutil.virtual_memory()
        # Use the Windows system drive when running on Windows.
        disk_path = os.environ.get("SystemDrive", "C:") + os.sep if os.name == "nt" else "/"
        disk = psutil.disk_usage(disk_path)

        status_text = (
            "📊 System status:\n\n"
            f"💻 CPU usage: {cpu_usage}%\n"
            f"🧠 RAM usage: {ram.percent}% "
            f"({ram.used / (1024**3):.2f} GB / {ram.total / (1024**3):.2f} GB)\n"
            f"💽 Disk ({disk_path}): {disk.percent}% "
            f"({disk.used / (1024**3):.2f} GB / {disk.total / (1024**3):.2f} GB)\n"
            f"⚙️ Total processes: {len(psutil.pids())}"
        )
        bot.send_message(message.chat.id, status_text)
    except Exception as error:
        bot.send_message(message.chat.id, f"Error getting system status: {error}")


@bot.message_handler(commands=["topcpu"])
def send_top_cpu(message):
    if not is_authorized(message.from_user.id):
        return

    bot.send_message(message.chat.id, "Collecting process information...")
    processes = get_processes_info()
    processes.sort(key=lambda item: item["cpu"], reverse=True)

    markup = types.InlineKeyboardMarkup()
    response = "🔥 Top 10 processes by CPU usage:\n\n"

    for process in processes[:10]:
        response += (
            f"• [{process['pid']}] {process['name']} — "
            f"{process['cpu']:.1f}% CPU (RAM: {process['mem']:.1f}%)\n"
        )
        markup.add(types.InlineKeyboardButton(
            f"🛑 Terminate {process['name']} (PID: {process['pid']})",
            callback_data=f"req_kill_{process['pid']}",
        ))

    bot.send_message(message.chat.id, response, reply_markup=markup)


@bot.message_handler(commands=["topram"])
def send_top_ram(message):
    if not is_authorized(message.from_user.id):
        return

    bot.send_message(message.chat.id, "Collecting process information...")
    processes = get_processes_info()
    processes.sort(key=lambda item: item["mem"], reverse=True)

    markup = types.InlineKeyboardMarkup()
    response = "💾 Top 10 processes by RAM usage:\n\n"

    for process in processes[:10]:
        response += (
            f"• [{process['pid']}] {process['name']} — "
            f"{process['mem']:.1f}% RAM (CPU: {process['cpu']:.1f}%)\n"
        )
        markup.add(types.InlineKeyboardButton(
            f"🛑 Terminate {process['name']} (PID: {process['pid']})",
            callback_data=f"req_kill_{process['pid']}",
        ))

    bot.send_message(message.chat.id, response, reply_markup=markup)


@bot.message_handler(commands=["search"])
def search_cmd(message):
    if not is_authorized(message.from_user.id):
        return

    query = message.text.partition(" ")[2].strip()
    if not query:
        user_states[message.from_user.id] = "awaiting_search"
        bot.send_message(message.chat.id, "Enter a process name or part of its name:")
    else:
        execute_search(message.chat.id, query)


@bot.message_handler(commands=["kill"])
def kill_cmd(message):
    if not is_authorized(message.from_user.id):
        return

    args = message.text.split()
    if len(args) < 2 or not args[1].isdigit():
        bot.send_message(message.chat.id, "Please provide a PID. Example: /kill 1234")
        return

    confirm_kill_request(message.chat.id, int(args[1]))


def execute_search(chat_id, query):
    found = []
    query_lower = query.lower()

    for process in psutil.process_iter(["pid", "name"]):
        try:
            process_name = process.info["name"] or ""
            if query_lower in process_name.lower():
                found.append((process.info["pid"], process_name))
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

    if not found:
        bot.send_message(chat_id, f"No processes found containing '{query}'.")
        return

    response = f"🔍 Found {len(found)} process(es); showing the first 15:\n\n"
    markup = types.InlineKeyboardMarkup()

    for pid, name in found[:15]:
        response += f"• PID: {pid} | Name: {name}\n"
        markup.add(types.InlineKeyboardButton(
            f"🛑 Terminate {name} (PID: {pid})",
            callback_data=f"req_kill_{pid}",
        ))

    bot.send_message(chat_id, response, reply_markup=markup)


def confirm_kill_request(chat_id, pid):
    try:
        process = psutil.Process(pid)
        name = process.name()

        markup = types.InlineKeyboardMarkup()
        yes_button = types.InlineKeyboardButton(
            "✅ Yes, terminate", callback_data=f"confirm_kill_{pid}"
        )
        no_button = types.InlineKeyboardButton(
            "❌ Cancel", callback_data="cancel_kill"
        )
        markup.row(yes_button, no_button)

        confirmation_text = (
            "⚠️ Are you sure you want to force-terminate this process?\n\n"
            f"Name: {name}\nPID: {pid}"
        )
        bot.send_message(chat_id, confirmation_text, reply_markup=markup)
    except psutil.NoSuchProcess:
        bot.send_message(chat_id, f"❌ Process with PID {pid} was not found.")
    except psutil.AccessDenied:
        bot.send_message(chat_id, f"❌ Access denied for process with PID {pid}.")


@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call):
    if not is_authorized(call.from_user.id):
        bot.answer_callback_query(call.id, "❌ Access denied.", show_alert=True)
        return

    data = call.data

    if data.startswith("req_kill_"):
        pid = int(data.split("_")[2])
        bot.answer_callback_query(call.id)
        confirm_kill_request(call.message.chat.id, pid)

    elif data.startswith("confirm_kill_"):
        pid = int(data.split("_")[2])
        try:
            process = psutil.Process(pid)
            process_name = process.name()
            process.terminate()
            _, still_alive = psutil.wait_procs([process], timeout=1)
            if still_alive:
                process.kill()

            bot.edit_message_text(
                f"✅ Process '{process_name}' (PID: {pid}) was terminated.",
                call.message.chat.id,
                call.message.message_id,
            )
            bot.answer_callback_query(call.id, "Process terminated.")
        except psutil.NoSuchProcess:
            bot.edit_message_text(
                f"ℹ️ Process with PID {pid} no longer exists.",
                call.message.chat.id,
                call.message.message_id,
            )
        except psutil.AccessDenied:
            bot.edit_message_text(
                f"❌ Not enough permissions to terminate PID {pid}.",
                call.message.chat.id,
                call.message.message_id,
            )
        except Exception as error:
            bot.edit_message_text(
                f"❌ Could not terminate the process: {error}",
                call.message.chat.id,
                call.message.message_id,
            )

    elif data == "cancel_kill":
        bot.edit_message_text(
            "❌ Process termination cancelled.",
            call.message.chat.id,
            call.message.message_id,
        )
        bot.answer_callback_query(call.id, "Cancelled")


@bot.message_handler(content_types=["text"])
def handle_text(message):
    if not is_authorized(message.from_user.id):
        return

    user_id = message.from_user.id
    text = message.text

    if user_states.get(user_id) == "awaiting_search":
        user_states[user_id] = None
        execute_search(message.chat.id, text)
        return

    if text == "📊 System status":
        send_status(message)
    elif text == "🔍 Search process":
        user_states[user_id] = "awaiting_search"
        bot.send_message(message.chat.id, "Enter a process name or part of its name:")
    elif text == "🔥 Top CPU":
        send_top_cpu(message)
    elif text == "💾 Top RAM":
        send_top_ram(message)
    else:
        bot.send_message(
            message.chat.id,
            "Choose an option from the menu or use /help.",
            reply_markup=get_main_keyboard(),
        )


def monitor_resources():
    """Monitor system load and send alerts when CPU or RAM usage is high."""
    last_alert_time = 0
    threshold_percent = 85.0
    alert_interval = 300  # Send alerts no more than once every 5 minutes.

    while True:
        try:
            cpu = psutil.cpu_percent(interval=1)
            ram = psutil.virtual_memory().percent

            if (
                (cpu > threshold_percent or ram > threshold_percent)
                and time.time() - last_alert_time > alert_interval
            ):
                alert_message = (
                    "🚨 WARNING: High system load!\n\n"
                    f"💻 CPU: {cpu}%\n"
                    f"🧠 RAM: {ram}%\n\n"
                    "Check /topcpu or /topram to identify resource-heavy processes."
                )
                try:
                    bot.send_message(ADMIN_ID, alert_message)
                    last_alert_time = time.time()
                except Exception as error:
                    print(f"Error sending alert: {error}")
        except Exception as error:
            print(f"Error in monitoring thread: {error}")

        time.sleep(10)


if __name__ == "__main__":
    monitor_thread = threading.Thread(target=monitor_resources, daemon=True)
    monitor_thread.start()

    print("Bot is running and ready.")

    try:
        bot.infinity_polling(skip_pending=True)
    except Exception as error:
        print(f"Bot runtime error: {error}")
