from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application

from app.redis_store import RedisStore
from app.utils import extract_message_id_from_link


class Poster:
    def __init__(
        self,
        application: Application,
        holding_chat_id: int,
        staging_chat_id: int,
        store: RedisStore,
    ) -> None:
        self.application = application
        self.holding_chat_id = holding_chat_id
        self.staging_chat_id = staging_chat_id
        self.store = store

    def _reply_markup(self, post) -> InlineKeyboardMarkup | None:
        if post.button_text.strip() and post.button_url.strip():
            return InlineKeyboardMarkup(
                [[InlineKeyboardButton(text=post.button_text.strip(), url=post.button_url.strip())]]
            )
        return None

    def _album_followup_text(self, post) -> str:
        text = (post.caption or "").strip()
        if text:
            return text
        if (post.button_text or "").strip() or (post.button_url or "").strip():
            return "Open below 👇"
        return ""

    async def send(self, post) -> int:
        media_type = post.media_type.strip().lower()
        reply_markup = self._reply_markup(post)

        if media_type == "text only":
            message = await self.application.bot.send_message(
                chat_id=self.holding_chat_id,
                text=post.caption,
                reply_markup=reply_markup,
                disable_web_page_preview=False,
            )
            return message.message_id

        if media_type == "staging post":
            source_message_id = extract_message_id_from_link(post.staging_post_link)

            copied = await self.application.bot.copy_message(
                chat_id=self.holding_chat_id,
                from_chat_id=self.staging_chat_id,
                message_id=source_message_id,
                reply_markup=reply_markup if not post.caption.strip() else None,
            )

            copied_message_id = copied.message_id

            if post.caption.strip():
                await self.application.bot.edit_message_caption(
                    chat_id=self.holding_chat_id,
                    message_id=copied_message_id,
                    caption=post.caption,
                    reply_markup=reply_markup,
                )

            return copied_message_id

        if media_type == "staging album":
            seed_message_id = extract_message_id_from_link(post.staging_post_link)
            album_message_ids = self.store.get_cached_album_message_ids(seed_message_id)

            if not album_message_ids:
                raise ValueError(
                    "No cached album members found for this seed link. Make sure the bot was running "
                    "and already in the staging channel when the album was posted, then use the first album message link."
                )

            copied = await self.application.bot.copy_messages(
                chat_id=self.holding_chat_id,
                from_chat_id=self.staging_chat_id,
                message_ids=album_message_ids,
            )

            first_message_id = copied[0].message_id if copied else 0

            followup_text = self._album_followup_text(post)
            if followup_text or reply_markup:
                followup = await self.application.bot.send_message(
                    chat_id=self.holding_chat_id,
                    text=followup_text or "Open below 👇",
                    reply_markup=reply_markup,
                    disable_web_page_preview=False,
                )
                return followup.message_id

            return first_message_id

        raise ValueError(f"Unsupported media type: {post.media_type}")
