"""
AttendBot — Telegram Attendance Bot
====================================
A frictionless daily attendance tracker for small teams.

SETUP
-----
1. pip install python-telegram-bot gspread google-auth
2. Create a bot via @BotFather on Telegram → get BOT_TOKEN
3. Set up Google Sheets API credentials (see README)
4. Fill in the config section below
5. python bot.py

HOW IT WORKS
------------
- Each morning at 9 AM the bot sends every registered employee a message
  with two buttons: ✅ Present  |  🏖 On Leave
- One tap records attendance. Employees get instant confirmation + leave balance.
- Admins can pull a full team report at any time with /report
- Data is written to Google Sheets in real time (no manual work)
"""

import logging
import json
import os
from datetime import datetime, date, timedelta
from zoneinfo import ZoneInfo
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    ContextTypes, JobQueue
)
import gspread
from google.oauth2.service_account import Credentials

# ─────────────────────────────────────────────
#  CONFIGURATION  (fill these in before running)
# ─────────────────────────────────────────────
BOT_TOKEN = "8625866977:AAEbLB61DsFF8Te6GDaM0P8esf2srHMjiEc"          # from @BotFather
GOOGLE_CREDS_FILE = "google_credentials1.json"  # service-account JSON
SPREADSHEET_ID = "1BcdQ-migXlvghiA9HgibZyeiLmerbQMKa4ny-FMs_JY"        # from the sheet URL
TIMEZONE = ZoneInfo("Asia/Kolkata")
POLL_HOUR = 9          # 9 AM
POLL_MINUTE = 0
LEAVES_PER_MONTH = 4

# Admin Telegram user IDs (get yours by messaging @userinfobot)
ADMIN_IDS = [1200126277]   # replace with real admin IDs

# Pre-register employees: {telegram_user_id: "Display Name"}
# Employees can also self-register with /register
EMPLOYEES = {
    # 987654321: "Priya Sharma",
    # 111222333: "Arun Menon",
}
# ─────────────────────────────────────────────

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ── In-memory store (replace with DB for production) ──────────────────────────
# Structure: { "YYYY-MM": { user_id: {"name": str, "days": {"YYYY-MM-DD": "present"|"leave"}} } }
attendance_data: dict = {}
employees: dict = dict(EMPLOYEES)  # mutable copy

# ── Google Sheets helper ───────────────────────────────────────────────────────
def get_sheet():
    scopes = ["https://www.googleapis.com/auth/spreadsheets"]
    creds = Credentials.from_service_account_file(GOOGLE_CREDS_FILE, scopes=scopes)
    client = gspread.authorize(creds)
    return client.open_by_key(SPREADSHEET_ID)

def write_to_sheet(user_id: int, name: str, date_str: str, status: str):
    """Append or update a row in the sheet."""
    try:
        sh = get_sheet()
        month = date_str[:7]
        # Each month gets its own worksheet tab
        try:
            ws = sh.worksheet(month)
        except gspread.WorksheetNotFound:
            ws = sh.add_worksheet(title=month, rows=500, cols=10)
            ws.append_row(["Employee ID", "Name", "Date", "Status", "Recorded At"])
        # Check if row already exists
        records = ws.get_all_records()
        for i, row in enumerate(records, start=2):
            if str(row.get("Employee ID")) == str(user_id) and row.get("Date") == date_str:
                ws.update(f"C{i}:E{i}", [[date_str, status, datetime.now().isoformat()]])
                return
        ws.append_row([user_id, name, date_str, status, datetime.now().isoformat()])
    except Exception as e:
        logger.error(f"Google Sheets error: {e}")

# ── Attendance logic ───────────────────────────────────────────────────────────
def record_attendance(user_id: int, name: str, date_str: str, status: str):
    month = date_str[:7]
    if month not in attendance_data:
        attendance_data[month] = {}
    if user_id not in attendance_data[month]:
        attendance_data[month][user_id] = {"name": name, "days": {}}
    attendance_data[month][user_id]["days"][date_str] = status
    write_to_sheet(user_id, name, date_str, status)

def get_leave_balance(user_id: int, month: str = None) -> dict:
    if month is None:
        month = date.today().strftime("%Y-%m")
    if month not in attendance_data or user_id not in attendance_data[month]:
        return {"leaves_taken": 0, "leaves_remaining": LEAVES_PER_MONTH, "days_present": 0}
    days = attendance_data[month][user_id]["days"]
    leaves_taken = sum(1 for s in days.values() if s == "leave")
    days_present = sum(1 for s in days.values() if s == "present")
    return {
        "leaves_taken": leaves_taken,
        "leaves_remaining": max(0, LEAVES_PER_MONTH - leaves_taken),
        "days_present": days_present
    }

def get_working_days_this_month() -> list[str]:
    """Return all working days (Mon–Fri) in the current month up to today."""
    today = date.today()
    first = today.replace(day=1)
    working = []
    d = first
    while d <= today:
        if d.weekday() < 5:  # Mon=0 … Fri=4
            working.append(d.strftime("%Y-%m-%d"))
        d += timedelta(days=1)
    return working

def is_working_day(d: date = None) -> bool:
    if d is None:
        d = date.today()
    return d.weekday() < 5  # Monday–Friday

# ── Keyboard helpers ───────────────────────────────────────────────────────────
def attendance_keyboard(date_str: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("✅  Present", callback_data=f"att|present|{date_str}"),
        InlineKeyboardButton("🏖  On Leave", callback_data=f"att|leave|{date_str}"),
    ]])

# ── Command handlers ───────────────────────────────────────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    msg = (
        f"👋 Hi {user.first_name}! I'm *AttendBot*.\n\n"
        "I'll send you a quick message every working morning so you can mark "
        "your attendance in one tap — no forms, no apps.\n\n"
        "Commands you can use:\n"
        "• /register — join the attendance system\n"
        "• /status — see your attendance & leave balance\n"
        "• /mark — mark today's attendance manually\n"
        "• /report — team report _(admins only)_\n"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")

async def register(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id in employees:
        await update.message.reply_text(
            f"✅ You're already registered as *{employees[user.id]}*.", parse_mode="Markdown"
        )
        return
    name = user.full_name or user.first_name
    employees[user.id] = name
    await update.message.reply_text(
        f"🎉 Registered! I'll track attendance for *{name}*.\n"
        "Every working day morning you'll get a message to mark your status.",
        parse_mode="Markdown"
    )

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id not in employees:
        await update.message.reply_text("You're not registered. Use /register first.")
        return
    bal = get_leave_balance(user.id)
    month = date.today().strftime("%B %Y")
    today_str = date.today().strftime("%Y-%m-%d")
    month_key = date.today().strftime("%Y-%m")
    today_status = "—"
    if month_key in attendance_data and user.id in attendance_data[month_key]:
        today_status = attendance_data[month_key][user.id]["days"].get(today_str, "—")
        today_status = "✅ Present" if today_status == "present" else ("🏖 On Leave" if today_status == "leave" else "—")
    msg = (
        f"📋 *Your Attendance — {month}*\n\n"
        f"Today: {today_status}\n"
        f"Days present: {bal['days_present']}\n"
        f"Leaves taken: {bal['leaves_taken']} / {LEAVES_PER_MONTH}\n"
        f"Leaves remaining: *{bal['leaves_remaining']}*"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")

async def mark(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id not in employees:
        await update.message.reply_text("You're not registered. Use /register first.")
        return
    today = date.today()
    if not is_working_day(today):
        await update.message.reply_text("Today is a weekend — no attendance needed! 🎉")
        return
    date_str = today.strftime("%Y-%m-%d")
    await update.message.reply_text(
        f"📅 *{today.strftime('%A, %d %B %Y')}*\n\nMark your attendance for today:",
        parse_mode="Markdown",
        reply_markup=attendance_keyboard(date_str)
    )

async def report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id not in ADMIN_IDS:
        await update.message.reply_text("⛔ This command is for admins only.")
        return
    month = date.today().strftime("%Y-%m")
    month_label = date.today().strftime("%B %Y")
    working_days = get_working_days_this_month()
    lines = [f"📊 *Team Report — {month_label}*\n"]
    if not employees:
        lines.append("No employees registered yet.")
    else:
        for uid, name in employees.items():
            bal = get_leave_balance(uid, month)
            # Count how many working days have no record (absent/not marked)
            if month in attendance_data and uid in attendance_data[month]:
                marked = attendance_data[month][uid]["days"]
            else:
                marked = {}
            unmarked = [d for d in working_days if d not in marked]
            status_icon = "✅" if bal['leaves_remaining'] > 0 else "⚠️"
            lines.append(
                f"{status_icon} *{name}*\n"
                f"   Present: {bal['days_present']}d  |  Leave: {bal['leaves_taken']}/{LEAVES_PER_MONTH}  |  "
                f"Balance: {bal['leaves_remaining']} left"
                + (f"\n   ⚠️ {len(unmarked)} day(s) unmarked" if unmarked else "")
            )
    await update.message.reply_text("\n\n".join(lines), parse_mode="Markdown")

# ── Callback: button taps ──────────────────────────────────────────────────────
async def button_tap(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = update.effective_user
    _, status_val, date_str = query.data.split("|")
    if user.id not in employees:
        await query.edit_message_text("You're not registered. Send /register first.")
        return
    name = employees[user.id]
    record_attendance(user.id, name, date_str, status_val)
    bal = get_leave_balance(user.id)
    icon = "✅" if status_val == "present" else "🏖"
    label = "Present" if status_val == "present" else "On Leave"
    day_label = datetime.strptime(date_str, "%Y-%m-%d").strftime("%A, %d %b")
    msg = (
        f"{icon} *{label}* recorded for {day_label}.\n\n"
        f"Leaves remaining this month: *{bal['leaves_remaining']}* / {LEAVES_PER_MONTH}"
    )
    await query.edit_message_text(msg, parse_mode="Markdown")

# ── Scheduled morning poll ─────────────────────────────────────────────────────
async def send_morning_poll(context: ContextTypes.DEFAULT_TYPE):
    today = date.today()
    if not is_working_day(today):
        return
    date_str = today.strftime("%Y-%m-%d")
    day_label = today.strftime("%A, %d %B %Y")
    for uid, name in employees.items():
        try:
            await context.bot.send_message(
                chat_id=uid,
                text=f"🌅 Good morning, {name.split()[0]}!\n\n📅 *{day_label}*\n\nAre you in today?",
                parse_mode="Markdown",
                reply_markup=attendance_keyboard(date_str)
            )
        except Exception as e:
            logger.warning(f"Could not message {name} ({uid}): {e}")

# ── Main ───────────────────────────────────────────────────────────────────────
def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("register", register))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("mark", mark))
    app.add_handler(CommandHandler("report", report))
    app.add_handler(CallbackQueryHandler(button_tap, pattern=r"^att\|"))
    # Schedule morning poll
    job_queue = app.job_queue
    job_queue.run_daily(
        send_morning_poll,
        time=datetime.now(TIMEZONE).replace(hour=POLL_HOUR, minute=POLL_MINUTE, second=0).timetz(),
        days=(0, 1, 2, 3, 4),  # Mon–Fri
    )
    logger.info("AttendBot is running…")
    app.run_polling()

if __name__ == "__main__":
    main()
