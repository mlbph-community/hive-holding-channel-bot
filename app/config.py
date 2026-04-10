from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional, Tuple
from zoneinfo import ZoneInfo

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    bot_token: str
    holding_chat_id: int
    staging_chat_id: int
    admin_chat_id: Optional[int]
    admin_user_ids: Tuple[int, ...]
    verification_bot_url: str
    apps_script_url: str
    apps_script_secret: str
    timezone_name: str
    schedule_tab_name: str
    poll_seconds: int
    upstash_redis_url: str
    posting_enabled: bool
    log_level: str

    @property
    def timezone(self) -> ZoneInfo:
        return ZoneInfo(self.timezone_name)


def _require(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def _optional_int(name: str) -> Optional[int]:
    raw = os.getenv(name, "").strip()
    if not raw:
        return None
    return int(raw)


def _int_tuple(name: str) -> Tuple[int, ...]:
    raw = os.getenv(name, "").strip()
    if not raw:
        return tuple()
    return tuple(int(x.strip()) for x in raw.split(",") if x.strip())


def _bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


def load_settings() -> Settings:
    load_dotenv()
    return Settings(
        bot_token=_require("BOT_TOKEN"),
        holding_chat_id=int(_require("HOLDING_CHAT_ID")),
        staging_chat_id=int(_require("STAGING_CHAT_ID")),
        admin_chat_id=_optional_int("ADMIN_CHAT_ID"),
        admin_user_ids=_int_tuple("ADMIN_USER_IDS"),
        verification_bot_url=_require("VERIFICATION_BOT_URL"),
        apps_script_url=_require("APPS_SCRIPT_URL"),
        apps_script_secret=_require("APPS_SCRIPT_SECRET"),
        timezone_name=os.getenv("TZ", "Asia/Manila").strip() or "Asia/Manila",
        schedule_tab_name=os.getenv("SCHEDULE_TAB_NAME", "Weekly Schedule").strip() or "Weekly Schedule",
        poll_seconds=int(os.getenv("POLL_SECONDS", "60")),
        upstash_redis_url=_require("UPSTASH_REDIS_URL"),
        posting_enabled=_bool("POSTING_ENABLED", True),
        log_level=os.getenv("LOG_LEVEL", "INFO").strip() or "INFO",
    )
