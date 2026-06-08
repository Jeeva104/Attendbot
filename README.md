# Attendbot
A Telegram bot that replaces manual WhatsApp attendance polls. Employees get a morning message with two buttons (✅ Present / 🏖 On Leave). One tap records attendance and shows remaining leave balance. Admins get a live team report with `/report`.
---

## Prerequisites
- Python 3.11+
- A Telegram account
- A Google account (for Sheets sync — optional but recommended)

---

## Step 1: Create the Telegram Bot
1. Open Telegram, search for **@BotFather**
2. Send `/newbot`, follow prompts, get your `BOT_TOKEN`
3. Paste it into `bot.py` → `BOT_TOKEN = "..."`

## Step 2: Install dependencies
```bash
pip install python-telegram-bot[job-queue] gspread google-auth
```

## Step 3: Google Sheets (optional but recommended)
1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a project → enable **Google Sheets API**
3. Create a **Service Account** → download JSON key as `google_credentials.json`
4. Create a new Google Sheet, share it with the service account email (Editor)
5. Copy the Sheet ID from the URL and paste into `bot.py` → `SPREADSHEET_ID = "..."`

## Step 4: Configure
In `bot.py`, set:
- `BOT_TOKEN` — from BotFather
- `ADMIN_IDS` — list of Telegram user IDs for admins (get yours from @userinfobot)
- `TIMEZONE` — your local timezone string (e.g. `"Asia/Kolkata"`)
- `POLL_HOUR` — what hour to send the morning message (default: 9)

## Step 5: Run
```bash
python bot.py
```

---

## Employee onboarding
1. Share the bot link (e.g. `t.me/YourAttendBot`) with all employees
2. They send `/start` then `/register`
3. Done — they'll receive the morning poll every working day

## Admin commands
| Command | What it does |
|---------|-------------|
| `/report` | Full team attendance + leave summary for current month |

## Employee commands
| Command | What it does |
|---------|-------------|
| `/register` | Join the system |
| `/status` | View your attendance + leave balance |
| `/mark` | Mark today's attendance manually (if you missed the morning message) |

---
