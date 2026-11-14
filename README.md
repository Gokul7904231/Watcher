# Watcher ⚡

> **Instant job alerts sent directly to your phone the moment a matching role is posted.**

Checks company career pages every ~10 minutes and messages you immediately via Telegram or ntfy. Free and runs 24/7 on GitHub Actions with zero external dependencies.

---

## ✨ Features

- **Multi-ATS Support**: Native integration with Greenhouse, Lever, and Ashby job boards.
- **Custom RSS/Atom Feeds**: Support for Google Alerts, custom feeds, and boards.
- **Precision Keyword & Location Matching**: Fine-tune `include_title`, `exclude_title`, and target `locations`.
- **Zero External Dependencies**: Pure Python standard library (no pip packages required).
- **Automated 24/7 Monitoring**: Runs automatically via GitHub Actions every 10 minutes.
- **Instant Alerts**: Notifies via Telegram Bot or ntfy.sh with direct job links.
- **Deduplication**: Remembers already-seen jobs so you never get spammed.

---

## 🚀 Setup Guide

### 1. Configure Notifications

#### Option A: Telegram Bot (Recommended)
1. On Telegram, message [@BotFather](https://t.me/BotFather) and send `/newbot`.
2. Follow the prompts to create your bot and copy your **Bot Token**.
3. Start a chat with your new bot and send it any message (e.g. `hi`).
4. Visit `https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getUpdates` in your browser.
5. Locate `"chat":{"id": 123456789...}` — that integer is your **Chat ID**.

#### Option B: ntfy.sh (No account needed)
1. Install the [ntfy](https://ntfy.sh) mobile app.
2. Subscribe to a unique, hard-to-guess topic name (e.g., `watcher-alerts-xyz987`).
3. Set that topic name as `NTFY_TOPIC`.

---

### 2. Configure GitHub Actions Secrets

In your GitHub repository:
1. Navigate to **Settings** > **Secrets and variables** > **Actions**.
2. Click **New repository secret** and add:
   - `TELEGRAM_BOT_TOKEN` *(Your Telegram bot token)*
   - `TELEGRAM_CHAT_ID` *(Your Telegram chat ID)*
   - `NTFY_TOPIC` *(Optional if using ntfy)*

---

### 3. First Run

1. Go to the **Actions** tab in your repository.
2. Select the **jobwatch** workflow and click **Run workflow**.
3. The baseline run records all currently open roles into `seen.json` (no alert spam on existing listings).
4. Subsequent scheduled runs will ping you only when new matching postings appear.

---

## 🛠️ Local Development & Testing

You can run Watcher locally on your computer:

```bash
# 1. Copy the environment template
cp .env.example .env

# 2. Add your Telegram credentials into .env
# TELEGRAM_BOT_TOKEN=...
# TELEGRAM_CHAT_ID=...

# 3. Test notification delivery
python jobwatch.py --test-notify

# 4. Perform a dry run (prints matches without sending alerts or writing state)
python jobwatch.py --dry-run

# 5. Run a full check
python jobwatch.py
```

---

## 🏢 Adding Companies

To track a new company, open any job listing from their career page and check the URL:

- **Greenhouse**: `boards.greenhouse.io/<slug>` or `job-boards.greenhouse.io/<slug>`
- **Lever**: `jobs.lever.co/<slug>`
- **Ashby**: `jobs.ashbyhq.com/<slug>`

Add automatically via CLI:
```bash
python jobwatch.py --add https://jobs.lever.co/cred
```

Or manually append to `config.json`:
```json
{
  "name": "CRED",
  "ats": "lever",
  "slug": "cred"
}
```

---

## 🎯 Tuning Filters

Edit `config.json` to customize your search criteria:

```json
{
  "include_title": [
    "intern", "software engineer", "backend", "full stack", "ai engineer", "python"
  ],
  "exclude_title": [
    "senior", "lead", "manager", "director", "sales", "marketing"
  ],
  "locations": [
    "remote", "india", "bengaluru", "bangalore", "hyderabad", "pune"
  ]
}
```

---

## 📝 License

MIT License.
