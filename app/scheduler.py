from __future__ import annotations

import logging
from datetime import datetime

from telegram.ext import Application, CallbackContext

from app.models import ScheduledPost
from app.poster import Poster
from app.redis_store import RedisStore
from app.sheets import SheetsRepository

logger = logging.getLogger(__name__)


class SchedulerService:
    def __init__(
        self,
        application: Application,
        sheets: SheetsRepository,
        store: RedisStore,
        poster: Poster,
        timezone,
        admin_chat_id: int | None = None,
    ) -> None:
        self.application = application
        self.sheets = sheets
        self.store = store
        self.poster = poster
        self.timezone = timezone
        self.admin_chat_id = admin_chat_id

    async def notify_admin(self, text: str) -> None:
        if self.admin_chat_id:
            await self.application.bot.send_message(chat_id=self.admin_chat_id, text=text)

    def _safe_due(self, post: ScheduledPost, now: datetime) -> bool:
        try:
            return post.is_due(now, self.timezone)
        except Exception as exc:
            logger.warning(
                "Skipping invalid row %s (%s): %s",
                post.row_number,
                post.post_id or "<blank>",
                exc,
            )
            return False

    def _safe_target_chat_ids(self, post: ScheduledPost) -> list[int]:
        try:
            return self.poster.resolve_target_chat_ids(post)
        except Exception as exc:
            logger.warning(
                "Skipping invalid target on row %s (%s): %s",
                post.row_number,
                post.post_id or "<blank>",
                exc,
            )
            return []

    def _all_targets_already_sent(self, post: ScheduledPost) -> bool:
        target_chat_ids = self._safe_target_chat_ids(post)
        if not target_chat_ids:
            return False

        return all(self.store.was_sent_to(post.post_id, chat_id) for chat_id in target_chat_ids)

    def get_due_posts(self) -> list[ScheduledPost]:
        now = datetime.now(self.timezone)
        posts = self.sheets.list_posts()
        due_posts = []

        for post in posts:
            is_valid, _ = post.is_valid()
            if not is_valid:
                continue
            if not post.is_active():
                continue
            if not post.is_scheduled():
                continue
            if self._all_targets_already_sent(post):
                continue
            if self._safe_due(post, now):
                due_posts.append(post)

        due_posts.sort(key=lambda p: p.due_at(self.timezone))
        return due_posts

    async def run_pending(self, context: CallbackContext) -> None:
        if self.store.is_paused():
            logger.info("Posting is paused. Skipping cycle.")
            return

        due_posts = self.get_due_posts()
        if not due_posts:
            return

        for post in due_posts:
            valid, reason = post.is_valid()
            if not valid:
                logger.warning("Skipping row %s: %s", post.row_number, reason)
                self.sheets.update_status(post.row_number, "Failed")
                self.sheets.update_note(post.row_number, reason)
                continue

            target_chat_ids = self._safe_target_chat_ids(post)
            if not target_chat_ids:
                self.sheets.update_status(post.row_number, "Failed")
                self.sheets.update_note(post.row_number, "Invalid Target Channel or missing target chat ID")
                continue

            success_targets: list[int] = []
            failed_targets: list[tuple[int, str]] = []

            for chat_id in target_chat_ids:
                if self.store.was_sent_to(post.post_id, chat_id):
                    success_targets.append(chat_id)
                    continue

                try:
                    message_id = await self.poster.send(post, target_chat_id=chat_id)
                    self.store.mark_sent_to(post.post_id, chat_id, message_id)
                    self.store.clear_failed_to(post.post_id, chat_id)
                    logger.info(
                        "Sent post %s to chat %s as message %s",
                        post.post_id,
                        chat_id,
                        message_id,
                    )
                    success_targets.append(chat_id)
                except Exception as exc:
                    error_text = str(exc)
                    logger.exception("Failed to send post %s to chat %s", post.post_id, chat_id)
                    self.store.mark_failed_to(post.post_id, chat_id, error_text)
                    failed_targets.append((chat_id, error_text))

            if success_targets and not failed_targets:
                self.sheets.update_status(post.row_number, "Sent")
                self.sheets.update_note(
                    post.row_number,
                    f"Sent successfully to target chat IDs: {', '.join(str(x) for x in success_targets)}",
                )
                continue

            if failed_targets and not success_targets:
                self.sheets.update_status(post.row_number, "Failed")
                self.sheets.update_note(
                    post.row_number,
                    "Failed on all targets: "
                    + " | ".join(f"{chat_id}: {error[:200]}" for chat_id, error in failed_targets),
                )
                await self.notify_admin(
                    f"Failed to send {post.post_id} on all targets: "
                    + " | ".join(f"{chat_id}: {error[:200]}" for chat_id, error in failed_targets)
                )
                continue

            self.sheets.update_status(post.row_number, "Partial")
            self.sheets.update_note(
                post.row_number,
                f"Sent to: {', '.join(str(x) for x in success_targets)} | "
                f"Failed on: {' | '.join(f'{chat_id}: {error[:200]}' for chat_id, error in failed_targets)}",
            )
            await self.notify_admin(
                f"Partial send for {post.post_id}. "
                f"Sent to: {', '.join(str(x) for x in success_targets)} | "
                f"Failed on: {' | '.join(f'{chat_id}: {error[:200]}' for chat_id, error in failed_targets)}"
            )
