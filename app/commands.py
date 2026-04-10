from __future__ import annotations

import asyncio
import logging
from datetime import datetime

from telegram import Update
from telegram.error import TimedOut
from telegram.ext import CallbackContext, CommandHandler

from app.redis_store import RedisStore
from app.scheduler import SchedulerService
from app.sheets import SheetsRepository
from app.utils import admin_only

logger = logging.getLogger(__name__)


async def safe_reply(message, text: str) -> None:
    for attempt in range(2):
        try:
            await message.reply_text(
                text,
                read_timeout=60,
                write_timeout=60,
                connect_timeout=20,
                pool_timeout=20,
            )
            return
        except TimedOut:
            if attempt == 0:
                logger.warning("Telegram reply timed out, retrying once.")
                await asyncio.sleep(1.5)
                continue
            raise


def _ensure_admin(update: Update, admin_user_ids: tuple[int, ...]) -> bool:
    user_id = update.effective_user.id if update.effective_user else None
    return admin_only(user_id, admin_user_ids)


def safe_due_at(post, timezone):
    try:
        return post.due_at(timezone)
    except Exception as exc:
        logger.warning(
            "Skipping invalid row for post_id=%s: %s",
            getattr(post, "post_id", "<blank>"),
            exc,
        )
        return None


def _format_post_line(post, due_dt) -> str:
    due_text = due_dt.strftime("%Y-%m-%d %H:%M")
    return f"• {post.post_id} | {due_text} | {post.content_type} | {post.theme or 'No theme'}"


def build_handlers(
    store: RedisStore,
    sheets: SheetsRepository,
    scheduler_service: SchedulerService,
    admin_user_ids: tuple[int, ...],
    timezone,
):
    async def status_cmd(update: Update, context: CallbackContext) -> None:
        if not _ensure_admin(update, admin_user_ids):
            return

        paused = store.is_paused()
        now = datetime.now(timezone).strftime("%Y-%m-%d %H:%M:%S")
        ping = "OK" if store.ping() else "FAIL"
        health = sheets.health()
        sheet_tab = health.get("tab", sheets.tab_name)

        await safe_reply(
            update.effective_message,
            "\n".join(
                [
                    "Holding Channel Content Bot",
                    f"Time: {now}",
                    f"Paused: {'Yes' if paused else 'No'}",
                    f"Redis: {ping}",
                    f"Sheet tab: {sheet_tab}",
                ]
            ),
        )

    async def pause_cmd(update: Update, context: CallbackContext) -> None:
        if not _ensure_admin(update, admin_user_ids):
            return
        store.set_paused(True)
        await safe_reply(update.effective_message, "Scheduled posting is now paused.")

    async def resume_cmd(update: Update, context: CallbackContext) -> None:
        if not _ensure_admin(update, admin_user_ids):
            return
        store.set_paused(False)
        await safe_reply(update.effective_message, "Scheduled posting is now active.")

    async def today_cmd(update: Update, context: CallbackContext) -> None:
        if not _ensure_admin(update, admin_user_ids):
            return

        today = datetime.now(timezone).date()
        posts_for_today: list[tuple[object, datetime]] = []

        for p in sheets.list_posts():
            if not p.is_active() or not p.is_scheduled():
                continue

            due = safe_due_at(p, timezone)
            if due is None:
                continue

            if due.date() == today:
                posts_for_today.append((p, due))

        if not posts_for_today:
            await safe_reply(update.effective_message, "No active scheduled posts for today.")
            return

        posts_for_today.sort(key=lambda item: item[1])

        lines = ["Today's scheduled posts:"]
        lines.extend(_format_post_line(post, due) for post, due in posts_for_today)

        text = "\n".join(lines)
        if len(text) > 3500:
            text = text[:3500] + "\n\n...truncated"

        await safe_reply(update.effective_message, text)

    async def nextposts_cmd(update: Update, context: CallbackContext) -> None:
        if not _ensure_admin(update, admin_user_ids):
            return

        now = datetime.now(timezone)
        upcoming: list[tuple[object, datetime]] = []

        for p in sheets.list_posts():
            if not p.is_active() or not p.is_scheduled():
                continue

            due = safe_due_at(p, timezone)
            if due is None:
                continue

            if due >= now:
                upcoming.append((p, due))

        upcoming.sort(key=lambda item: item[1])
        upcoming = upcoming[:10]

        if not upcoming:
            await safe_reply(update.effective_message, "No upcoming active scheduled posts.")
            return

        lines = ["Next scheduled posts:"]
        lines.extend(_format_post_line(post, due) for post, due in upcoming)

        text = "\n".join(lines)
        if len(text) > 3500:
            text = text[:3500] + "\n\n...truncated"

        await safe_reply(update.effective_message, text)

    async def postnow_cmd(update: Update, context: CallbackContext) -> None:
        if not _ensure_admin(update, admin_user_ids):
            return

        if not context.args:
            await safe_reply(update.effective_message, "Usage: /postnow <POST_ID>")
            return

        target_post_id = context.args[0].strip()
        matches = [p for p in sheets.list_posts() if p.post_id == target_post_id]

        if not matches:
            await safe_reply(update.effective_message, f"Post ID not found: {target_post_id}")
            return

        post = matches[0]
        valid, reason = post.is_valid()
        if not valid:
            await safe_reply(update.effective_message, f"Cannot send {target_post_id}: {reason}")
            return

        try:
            message_id = await scheduler_service.poster.send(post)
            store.mark_sent(post.post_id, message_id)
            store.clear_failed(post.post_id)
            sheets.update_status(post.row_number, "Sent")
            sheets.update_note(post.row_number, f"Manually sent. Message ID: {message_id}")
            await safe_reply(update.effective_message, f"Sent {target_post_id} successfully.")
        except Exception as exc:
            sheets.update_status(post.row_number, "Failed")
            sheets.update_note(post.row_number, str(exc)[:1000])
            await safe_reply(update.effective_message, f"Failed to send {target_post_id}: {exc}")

    return [
        CommandHandler("status", status_cmd),
        CommandHandler("pause", pause_cmd),
        CommandHandler("resume", resume_cmd),
        CommandHandler("today", today_cmd),
        CommandHandler("nextposts", nextposts_cmd),
        CommandHandler("postnow", postnow_cmd),
    ]
