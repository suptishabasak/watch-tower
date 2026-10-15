import json
from datetime import datetime

from .models import Change, Monitor, Snapshot, display_status


def iso(dt: datetime | None) -> str | None:
    return dt.isoformat() + "Z" if dt else None


def _shot(name: str | None) -> str | None:
    return f"/screenshots/{name}" if name else None


def serialize_monitor(m: Monitor, change_count: int = 0) -> dict:
    return {
        "id": m.id,
        "name": m.name,
        "url": m.url,
        "interval_minutes": m.interval_minutes,
        "focus": m.focus,
        "sensitivity": m.sensitivity,
        "watch_selectors": json.loads(m.watch_selectors or "[]"),
        "ignore_selectors": json.loads(m.ignore_selectors or "[]"),
        "status": display_status(m),
        "paused": m.paused,
        "checking": m.checking,
        "last_error": m.last_error,
        "consecutive_failures": m.consecutive_failures,
        "created_at": iso(m.created_at),
        "last_checked_at": iso(m.last_checked_at),
        "next_check_at": iso(m.next_check_at),
        "last_changed_at": iso(m.last_changed_at),
        "unseen_changes": m.unseen_changes,
        "change_count": change_count,
        "notify_discord": m.notify_discord,
        "notify_email": m.notify_email,
        "notify_telegram": m.notify_telegram,
        "notify_on_error": m.notify_on_error,
        "has_custom_webhook": bool(m.discord_webhook_url),  # the URL itself is never returned
        "is_demo": m.is_demo,
    }


def serialize_change(c: Change) -> dict:
    data = json.loads(c.diff_json or "{}")
    return {
        "id": c.id,
        "detected_at": iso(c.detected_at),
        "summary": c.summary,
        "added_count": c.added_count,
        "removed_count": c.removed_count,
        "modified_count": c.modified_count,
        "changes": data.get("items", []),
        "omitted": data.get("omitted", 0),
        "before_screenshot": _shot(c.before_screenshot),
        "after_screenshot": _shot(c.after_screenshot),
        "notified": c.notified,
        "notification_note": c.notification_note,
    }


def serialize_snapshot(s: Snapshot, include_text: bool = False) -> dict:
    data = {
        "id": s.id,
        "created_at": iso(s.created_at),
        "content_hash": s.content_hash[:12],
        "screenshot": _shot(s.screenshot),
        "line_count": (s.text.count("\n") + 1) if s.text else 0,
    }
    if include_text:
        data["text"] = s.text
    return data
