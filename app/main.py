from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from telegram import BotCommand, Update
from telegram.ext import Application, ApplicationBuilder, Defaults, TypeHandler
from telegram.request import HTTPXRequest

from app.commands import build_handlers
from app.config import load_settings
from app.logging_setup import setup_logging
from app.poster import Poster
from app.redis_store import RedisStore
from app.scheduler import SchedulerService
from app.sheets import SheetsRepository

settings = load_settings()
setup_logging(settings.log_level)
logger = logging.getLogger(__name__)

telegram_app: Application | None = None


async def on_error(update, context) -> None:
    logger.exception("Unhandled bot error", exc_info=context.error)


async def cache_staging_channel_post(update: Update, context) -> None:
    message = update.channel_post
    if not message:
        return

    bot_settings = context.application.bot_data["settings"]
    store: RedisStore = context.application.bot_data["store"]

    if message.chat_id != bot_settings.staging_chat_id:
        return

    if message.media_group_id:
        store.cache_staging_album_member(
            message_id=message.message_id,
            media_group_id=message.media_group_id,
        )


async def start_telegram_bot() -> None:
    global telegram_app

    defaults = Defaults(tzinfo=settings.timezone)

    request = HTTPXRequest(
        connect_timeout=20.0,
        read_timeout=60.0,
        write_timeout=60.0,
        pool_timeout=20.0,
    )

    get_updates_request = HTTPXRequest(
        connect_timeout=20.0,
        read_timeout=60.0,
        write_timeout=60.0,
        pool_timeout=20.0,
    )

    telegram_app = (
        ApplicationBuilder()
        .token(settings.bot_token)
        .defaults(defaults)
        .request(request)
        .get_updates_request(get_updates_request)
        .build()
    )

    store = RedisStore(settings.upstash_redis_url)
    sheets = SheetsRepository(
        apps_script_url=settings.apps_script_url,
        secret=settings.apps_script_secret,
        tab_name=settings.schedule_tab_name,
    )
    poster = Poster(
        application=telegram_app,
        holding_chat_id=settings.holding_chat_id,
        staging_chat_id=settings.staging_chat_id,
        store=store,
    )
    scheduler_service = SchedulerService(
        application=telegram_app,
        sheets=sheets,
        store=store,
        poster=poster,
        timezone=settings.timezone,
        admin_chat_id=settings.admin_chat_id,
    )

    telegram_app.bot_data["settings"] = settings
    telegram_app.bot_data["store"] = store
    telegram_app.bot_data["sheets"] = sheets

    telegram_app.add_error_handler(on_error)
    telegram_app.add_handler(TypeHandler(Update, cache_staging_channel_post), group=-1)

    for handler in build_handlers(
        store=store,
        sheets=sheets,
        scheduler_service=scheduler_service,
        admin_user_ids=settings.admin_user_ids,
        timezone=settings.timezone,
    ):
        telegram_app.add_handler(handler)

    await telegram_app.bot.set_my_commands(
        [
            BotCommand("status", "Show bot health and pause state"),
            BotCommand("today", "Show today's scheduled posts"),
            BotCommand("nextposts", "Show upcoming scheduled posts"),
            BotCommand("pause", "Pause scheduled posting"),
            BotCommand("resume", "Resume scheduled posting"),
            BotCommand("postnow", "Manually send one post by ID"),
        ]
    )

    if settings.posting_enabled:
        telegram_app.job_queue.run_repeating(
            scheduler_service.run_pending,
            interval=settings.poll_seconds,
            first=5,
            name="schedule-poller",
        )
        logger.info("Scheduled polling is enabled. Interval: %s seconds", settings.poll_seconds)
    else:
        logger.warning("Scheduled polling is disabled by POSTING_ENABLED=false")

    await telegram_app.initialize()
    await telegram_app.start()
    await telegram_app.updater.start_polling(allowed_updates=Update.ALL_TYPES)

    logger.info("Holding Channel Content Bot is running as a web service.")


async def stop_telegram_bot() -> None:
    global telegram_app

    if not telegram_app:
        return

    logger.info("Stopping Telegram bot...")

    try:
        if telegram_app.updater and telegram_app.updater.running:
            await telegram_app.updater.stop()
    finally:
        if telegram_app.running:
            await telegram_app.stop()
        await telegram_app.shutdown()

    logger.info("Telegram bot stopped cleanly.")


@asynccontextmanager
async def lifespan(_: FastAPI):
    await start_telegram_bot()
    try:
        yield
    finally:
        await stop_telegram_bot()


app = FastAPI(lifespan=lifespan)


@app.api_route("/", methods=["GET", "HEAD"])
async def root():
    return {"ok": True, "service": "holding-channel-content-bot"}


@app.api_route("/healthz", methods=["GET", "HEAD"])
async def healthz():
    paused = False
    redis_ok = False

    try:
        store: RedisStore | None = telegram_app.bot_data.get("store") if telegram_app else None
        if store:
            paused = store.is_paused()
            redis_ok = store.ping()
    except Exception:
        logger.exception("Health check failed while reading bot state")

    return {
        "ok": True,
        "bot_running": bool(telegram_app and telegram_app.running),
        "paused": paused,
        "redis": redis_ok,
    }


if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", "10000")),
        log_level="info",
    )
