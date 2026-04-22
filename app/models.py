from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo


@dataclass(slots=True)
class ScheduledPost:
    row_number: int
    post_id: str
    date_text: str
    time_text: str
    target_channel_text: str
    content_type: str
    theme: str
    caption: str
    media_type: str
    staging_post_link: str
    button_text: str
    button_url: str
    active: str
    status: str
    notes: str

    def is_active(self) -> bool:
        return self.active.strip().lower() in {"yes", "true", "1", "active"}

    def is_scheduled(self) -> bool:
        return self.status.strip().lower() in {"scheduled", "partial"}

    def normalized_target_channel(self) -> str:
        return (self.target_channel_text or "").strip()

    def target_channel_labels(self) -> list[str]:
        value = self.normalized_target_channel()

        if value == "Holding Channel":
            return ["Holding Channel"]
        if value == "Melbet Philippines":
            return ["Melbet Philippines"]
        if value == "Both":
            return ["Holding Channel", "Melbet Philippines"]

        return []

    def normalized_time_text(self) -> str:
        raw = (self.time_text or "").strip()
        if len(raw) == 8 and raw.count(":") == 2:
            return raw[:5]
        return raw

    def due_at(self, tz: ZoneInfo) -> datetime:
        date_text = (self.date_text or "").strip()
        time_text = self.normalized_time_text()

        if not date_text or not time_text:
            raise ValueError(f"Missing date/time for post {self.post_id or '<blank>'}")

        dt = datetime.strptime(f"{date_text} {time_text}", "%Y-%m-%d %H:%M")
        return dt.replace(tzinfo=tz)

    def is_due(self, now: datetime, tz: ZoneInfo) -> bool:
        return self.due_at(tz) <= now

    def is_valid(self) -> tuple[bool, str]:
        if not self.post_id.strip():
            return False, "Missing Post ID"
        if not self.date_text.strip():
            return False, "Missing Date"
        if not self.time_text.strip():
            return False, "Missing Time (PHT)"

        target_value = self.normalized_target_channel()
        if target_value not in {"Holding Channel", "Melbet Philippines", "Both"}:
            return False, f"Invalid Target Channel: {target_value or '<blank>'}"

        media_type = self.media_type.strip().lower()
        if media_type == "text only" and not self.caption.strip():
            return False, "Text Only posts need a Caption"
        if media_type in {"staging post", "staging album"} and not self.staging_post_link.strip():
            return False, "Staging Post Link is required"
        if media_type not in {"text only", "staging post", "staging album"}:
            return False, f"Unsupported Media Type: {self.media_type}"
        return True, ""

    @classmethod
    def from_row(cls, row_number: int, row: dict) -> "ScheduledPost":
        return cls(
            row_number=row_number,
            post_id=str(row.get("Post ID", "")).strip(),
            date_text=str(row.get("Date", "")).strip(),
            time_text=str(row.get("Time (PHT)", "")).strip(),
            target_channel_text=str(row.get("Target Channel", "")).strip(),
            content_type=str(row.get("Content Type", "")).strip(),
            theme=str(row.get("Theme", "")).strip(),
            caption=str(row.get("Caption", "")).strip(),
            media_type=str(row.get("Media Type", "")).strip(),
            staging_post_link=str(row.get("Staging Post Link", "")).strip(),
            button_text=str(row.get("Button Text", "")).strip(),
            button_url=str(row.get("Button URL", "")).strip(),
            active=str(row.get("Active", "")).strip(),
            status=str(row.get("Status", "")).strip(),
            notes=str(row.get("Notes", "")).strip(),
        )
