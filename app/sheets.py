from __future__ import annotations

import logging
from typing import List

import requests

from app.models import ScheduledPost

logger = logging.getLogger(__name__)


class SheetsRepository:
    REQUIRED_HEADERS = [
        "Post ID",
        "Date",
        "Time (PHT)",
        "Content Type",
        "Theme",
        "Caption",
        "Media Type",
        "Staging Post Link",
        "Button Text",
        "Button URL",
        "Active",
        "Status",
        "Notes",
    ]

    def __init__(self, apps_script_url: str, secret: str, tab_name: str, timeout: int = 60) -> None:
        self.apps_script_url = apps_script_url.strip()
        self.secret = secret.strip()
        self.tab_name = tab_name.strip() or "Weekly Schedule"
        self.timeout = timeout

    def _get(self, params: dict) -> dict:
        payload = {**params, "secret": self.secret, "tab": self.tab_name}
        last_exc = None

        for _ in range(3):
            try:
                response = requests.get(self.apps_script_url, params=payload, timeout=self.timeout)
                response.raise_for_status()
                data = response.json()
                if not data.get("ok"):
                    raise RuntimeError(data.get("error", "Apps Script GET request failed"))
                return data
            except Exception as exc:
                last_exc = exc

        raise last_exc

    def _post(self, body: dict) -> dict:
        payload = {**body, "secret": self.secret, "tab": self.tab_name}
        last_exc = None

        for _ in range(3):
            try:
                response = requests.post(self.apps_script_url, json=payload, timeout=self.timeout)
                response.raise_for_status()
                data = response.json()
                if not data.get("ok"):
                    raise RuntimeError(data.get("error", "Apps Script POST request failed"))
                return data
            except Exception as exc:
                last_exc = exc

        raise last_exc

    def list_posts(self) -> List[ScheduledPost]:
        data = self._get({"action": "list_posts"})
        rows = data.get("posts", [])
        posts: List[ScheduledPost] = []
        for idx, row in enumerate(rows, start=2):
            posts.append(ScheduledPost.from_row(idx, row))
        return posts

    def update_status(self, row_number: int, status: str) -> None:
        self._post({
            "action": "update_status",
            "row_number": row_number,
            "status": status,
        })

    def update_note(self, row_number: int, note: str) -> None:
        self._post({
            "action": "update_note",
            "row_number": row_number,
            "note": note,
        })

    def health(self) -> dict:
        return self._get({"action": "health"})
