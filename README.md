# Holding Channel Content Bot

A Telegram bot for the **Holding Channel** that posts scheduled content from Google Sheets, reuses approved assets from a private staging channel, and sends verification reminders that point to a separate verification bot.

## What is included

- Scheduled posting via `python-telegram-bot` `JobQueue`
- Google Sheets schedule reader
- Redis-backed pause, resume, and dedupe state
- Support for:
  - text-only posts
  - staging-post copies from a private Telegram channel
  - optional CTA buttons
- Admin commands:
  - `/status`
  - `/pause`
  - `/resume`
  - `/today`
  - `/nextposts`
  - `/postnow <POST_ID>`

## Repo structure

```text
holding-channel-content-bot-starter/
├── app/
│   ├── __init__.py
│   ├── commands.py
│   ├── config.py
│   ├── logging_setup.py
│   ├── main.py
│   ├── models.py
│   ├── poster.py
│   ├── redis_store.py
│   ├── scheduler.py
│   ├── sheets.py
│   └── utils.py
├── docs/
│   └── sheet_template.md
├── tests/
│   └── test_utils.py
├── .env.example
├── .gitignore
├── render.yaml
├── requirements.txt
└── runtime.txt
```

## Required setup

### 1. Create the Telegram bot
Create the bot in BotFather and copy the token.

### 2. Create the Google Sheet
Create a spreadsheet with these tabs:

- `Weekly Schedule`
- `Templates`
- `Guide`

The bot reads the `Weekly Schedule` tab.

### 3. Create a Google service account
Create a service account, enable Sheets API access, and share the spreadsheet with the service account email.

### 4. Create the Redis database
Create an Upstash Redis database and copy the `rediss://` connection string.

### 5. Create the staging channel and Holding Channel
The bot needs:
- one private staging channel
- one Holding Channel group or supergroup
- optional admin chat for failure alerts

## Environment variables

Copy `.env.example` to `.env` and fill in the values.

Important fields:

- `BOT_TOKEN`
- `HOLDING_CHAT_ID`
- `STAGING_CHAT_ID`
- `VERIFICATION_BOT_URL`
- `APPS_SCRIPT_URL`
- `APPS_SCRIPT_SECRET`
- `UPSTASH_REDIS_URL`

## Render deployment

This repo includes a `render.yaml` blueprint for a **Background Worker**.

Recommended:
- create a GitHub repo
- push this code
- create the worker in Render
- set all environment variables
- deploy

## Notes

- The bot assumes the **staging post link** in the sheet points to a message inside the configured `STAGING_CHAT_ID`.
- The bot writes back status changes to the `Weekly Schedule` tab.
- The bot uses Asia/Manila by default.

## First commands to test

Once deployed and invited as an admin where needed:

- `/status`
- `/today`
- `/nextposts`

## Suggested next steps

1. Add your real bot token
2. Add your real Sheet ID
3. Share the sheet with your service account
4. Add the bot to the staging channel and Holding Channel
5. Promote the bot with the permissions it needs
6. Deploy to Render
