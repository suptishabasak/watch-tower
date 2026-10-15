from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def utcnow() -> datetime:
    """Naive UTC datetime (SQLite does not keep tzinfo). Serialised with a 'Z' suffix."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Monitor(Base):
    __tablename__ = "monitors"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80))
    url: Mapped[str] = mapped_column(String(2048))
    interval_minutes: Mapped[int] = mapped_column(Integer)
    focus: Mapped[str | None] = mapped_column(String(200), nullable=True)
    sensitivity: Mapped[int] = mapped_column(Integer, default=2)  # 1=strict, 2=balanced, 3=high signal
    watch_selectors: Mapped[str | None] = mapped_column(Text, nullable=True)
    ignore_selectors: Mapped[str | None] = mapped_column(Text, nullable=True)

    paused: Mapped[bool] = mapped_column(Boolean, default=False)
    checking: Mapped[bool] = mapped_column(Boolean, default=False)
    last_result: Mapped[str] = mapped_column(String(16), default="pending")  # pending | ok | error
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0)
    error_notified: Mapped[bool] = mapped_column(Boolean, default=False)
    unseen_changes: Mapped[int] = mapped_column(Integer, default=0)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    next_check_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    last_changed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Latest snapshot (the baseline the next check is compared against)
    last_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    last_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_screenshot: Mapped[str | None] = mapped_column(String(128), nullable=True)

    # Notification preferences. The webhook is write-only: never serialised to the API.
    notify_discord: Mapped[bool] = mapped_column(Boolean, default=True)
    notify_email: Mapped[bool] = mapped_column(Boolean, default=False)
    notify_telegram: Mapped[bool] = mapped_column(Boolean, default=False)
    notify_on_error: Mapped[bool] = mapped_column(Boolean, default=False)
    discord_webhook_url: Mapped[str | None] = mapped_column(String(300), nullable=True)

    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)

    changes: Mapped[list["Change"]] = relationship(
        back_populates="monitor", cascade="all, delete-orphan", order_by="Change.detected_at.desc()"
    )
    snapshots: Mapped[list["Snapshot"]] = relationship(
        back_populates="monitor", cascade="all, delete-orphan", order_by="Snapshot.created_at.desc()"
    )


class Snapshot(Base):
    """One stored version of a page: its cleaned text and screenshot. A new row is written only when the
    content hash changes, so the rows form the per-page version timeline and can be compared pairwise."""

    __tablename__ = "snapshots"

    id: Mapped[int] = mapped_column(primary_key=True)
    monitor_id: Mapped[int] = mapped_column(ForeignKey("monitors.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    content_hash: Mapped[str] = mapped_column(String(64), index=True)
    text: Mapped[str] = mapped_column(Text, default="")
    screenshot: Mapped[str | None] = mapped_column(String(128), nullable=True)

    monitor: Mapped["Monitor"] = relationship(back_populates="snapshots")


class Change(Base):
    __tablename__ = "changes"

    id: Mapped[int] = mapped_column(primary_key=True)
    monitor_id: Mapped[int] = mapped_column(ForeignKey("monitors.id", ondelete="CASCADE"), index=True)
    detected_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    summary: Mapped[str] = mapped_column(Text)
    added_count: Mapped[int] = mapped_column(Integer, default=0)
    removed_count: Mapped[int] = mapped_column(Integer, default=0)
    modified_count: Mapped[int] = mapped_column(Integer, default=0)
    diff_json: Mapped[str] = mapped_column(Text, default="{}")
    before_screenshot: Mapped[str | None] = mapped_column(String(128), nullable=True)
    after_screenshot: Mapped[str | None] = mapped_column(String(128), nullable=True)
    change_key: Mapped[str] = mapped_column(String(64), index=True)  # sha256(prev_hash:new_hash)
    notified: Mapped[bool] = mapped_column(Boolean, default=False)
    notification_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    monitor: Mapped[Monitor] = relationship(back_populates="changes")


def display_status(m: Monitor) -> str:
    if m.paused:
        return "paused"
    if m.checking:
        return "checking"
    if m.last_result == "error":
        return "error"
    if m.unseen_changes > 0:
        return "changed"
    if m.last_result == "ok":
        return "ok"
    return "pending"