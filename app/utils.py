from __future__ import annotations

import re
from typing import Optional


def extract_message_id_from_link(link: str) -> int:
    patterns = [
        r"https?://t\.me/c/\d+/(\d+)",
        r"https?://t\.me/[A-Za-z0-9_]+/(\d+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, link)
        if match:
            return int(match.group(1))
    raise ValueError(f"Could not extract message ID from link: {link}")


def admin_only(user_id: Optional[int], admin_user_ids: tuple[int, ...]) -> bool:
    if user_id is None:
        return False
    return user_id in admin_user_ids
