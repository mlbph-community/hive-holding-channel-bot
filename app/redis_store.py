from __future__ import annotations

from typing import Optional

from redis import Redis


class RedisStore:
    ALBUM_TTL_SECONDS = 7 * 24 * 60 * 60

    def __init__(self, redis_url: str) -> None:
        self.client = Redis.from_url(redis_url, decode_responses=True)

    def ping(self) -> bool:
        return bool(self.client.ping())

    def is_paused(self) -> bool:
        return self.client.get("bot:paused") == "1"

    def set_paused(self, paused: bool) -> None:
        self.client.set("bot:paused", "1" if paused else "0")

    def was_sent(self, post_id: str) -> bool:
        return self.client.get(f"post:{post_id}:sent") == "1"

    def mark_sent(self, post_id: str, message_id: int) -> None:
        pipe = self.client.pipeline()
        pipe.set(f"post:{post_id}:sent", "1")
        pipe.set(f"post:{post_id}:message_id", str(message_id))
        pipe.execute()

    def get_sent_message_id(self, post_id: str) -> Optional[str]:
        return self.client.get(f"post:{post_id}:message_id")

    def mark_failed(self, post_id: str, error_text: str) -> None:
        pipe = self.client.pipeline()
        pipe.set(f"post:{post_id}:failed", "1")
        pipe.set(f"post:{post_id}:error", error_text[:1000])
        pipe.execute()

    def clear_failed(self, post_id: str) -> None:
        pipe = self.client.pipeline()
        pipe.delete(f"post:{post_id}:failed")
        pipe.delete(f"post:{post_id}:error")
        pipe.execute()

    def cache_staging_album_member(self, message_id: int, media_group_id: str) -> None:
        group_key = f"staging:album:{media_group_id}"
        member_key = f"staging:album_member:{message_id}"

        pipe = self.client.pipeline()
        pipe.setex(member_key, self.ALBUM_TTL_SECONDS, media_group_id)
        pipe.rpush(group_key, message_id)
        pipe.expire(group_key, self.ALBUM_TTL_SECONDS)
        pipe.execute()

    def get_cached_album_message_ids(self, seed_message_id: int) -> list[int]:
        group_id = self.client.get(f"staging:album_member:{seed_message_id}")
        if not group_id:
            return []

        raw_ids = self.client.lrange(f"staging:album:{group_id}", 0, -1)
        cleaned: list[int] = []

        for item in raw_ids:
            cleaned.append(int(item))

        return sorted(set(cleaned))
