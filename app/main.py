from __future__ import annotations

import asyncio
import logging

from telegram import BotCommand, Update
from telegram.ext import ApplicationBuilder, Defaults, TypeHandler
from telegram.request import HTTPXRequest

from app.commands import build_handlers
from app.config import load_settings
from app.logging_setup import setup_logging
from app.poster import Poster
from app.redis_store import RedisStore
from app.scheduler import SchedulerService
from app.sheets import SheetsRepository

logger = logging.getLogger(__name__)


async def on_error(update, context) -> None:
    logger.exception("Unhandled bot error", exc_info=context.error)


async def cache_staging_channel_post(update: Update, context) -> None:
    message = update.channel_post
    if not message:
        return

    settings = context.application.bot_data["settings"]
    store: RedisStore = context.application.bot_data["store"]

    if message.chat_id != settings.staging_chat_id:
        return

    if message.media_group_id:
        store.cache_staging_album_member(
            message_id=message.message_id,
            media_group_id=message.media_group_id,
        )


async def main() -> None:
    settings = load_settings()
    setup_logging(settings.log_level)

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

    application = (
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
        application=application,
        holding_chat_id=settings.holding_chat_id,
        staging_chat_id=settings.staging_chat_id,
        store=store,
    )
    scheduler_service = SchedulerService(
        application=application,
        sheets=sheets,
        store=store,
        poster=poster,
        timezone=settings.timezone,
        admin_chat_id=settings.admin_chat_id,
    )

    application.bot_data["settings"] = settings
    application.bot_data["store"] = store
    application.bot_data["sheets"] = sheets

    application.add_error_handler(on_error)
    application.add_handler(TypeHandler(Update, cache_staging_channel_post), group=-1)

    for handler in build_handlers(
        store=store,
        sheets=sheets,
        scheduler_service=scheduler_service,
        admin_user_ids=settings.admin_user_ids,
        timezone=settings.timezone,
    ):
        application.add_handler(handler)

    await application.initialize()
    await application.bot.set_my_commands(
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
        application.job_queue.run_repeating(
            scheduler_service.run_pending,
            interval=settings.poll_seconds,
            first=5,
            name="schedule-poller",
        )
        logger.info("Scheduled polling is enabled. Interval: %s seconds", settings.poll_seconds)
    else:
        logger.warning("Scheduled polling is disabled by POSTING_ENABLED=false")

    await application.start()
    await application.updater.start_polling(allowed_updates=Update.ALL_TYPES)

    logger.info("Holding Channel Content Bot is running.")
    try:
        await asyncio.Event().wait()
    finally:
        await application.updater.stop()
        await application.stop()
        await application.shutdown()

if __name__ == "__main__":
    asyncio.run(main())