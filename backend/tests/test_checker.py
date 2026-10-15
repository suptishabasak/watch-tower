from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app import models  # noqa: F401  (registers tables)
from app.checker import apply_failure, apply_snapshot
from app.database import Base
from app.models import Change, Monitor
from app.notifications.base import Notifier

T0 = datetime(2026, 3, 1, 12, 0, 0)


class FakeNotifier(Notifier):
    name = "fake"

    def __init__(self):
        self.events = []

    def send(self, event):
        self.events.append(event)


@pytest.fixture
def db():
    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as session:
        yield session


def make_monitor(db, **kw):
    m = Monitor(name="Shop", url="https://example.com/p", interval_minutes=60, next_check_at=T0, **kw)
    db.add(m)
    db.commit()
    return m


def changes(db):
    return db.scalars(select(Change).order_by(Change.id)).all()


PAGE_A = "Shoe\nPrice: $10.00\nIn stock"
PAGE_B = "Shoe\nPrice: $12.00\nIn stock"


def test_first_check_is_baseline_without_change_or_notification(db):
    m, n = make_monitor(db), FakeNotifier()
    out = apply_snapshot(db, m, PAGE_A, None, now=T0, notifiers=[n])
    assert out.kind == "baseline"
    assert changes(db) == [] and n.events == []
    assert m.last_hash and m.last_result == "ok"
    assert m.next_check_at == T0 + timedelta(minutes=60)


def test_unchanged_content_creates_nothing(db):
    m, n = make_monitor(db), FakeNotifier()
    apply_snapshot(db, m, PAGE_A, None, now=T0, notifiers=[n])
    out = apply_snapshot(db, m, PAGE_A, None, now=T0 + timedelta(hours=1), notifiers=[n])
    assert out.kind == "unchanged"
    assert changes(db) == [] and n.events == []


def test_timestamp_only_difference_is_not_a_change(db):
    m, n = make_monitor(db), FakeNotifier()
    apply_snapshot(db, m, "Shoe\nUpdated 5 minutes ago", None, now=T0, notifiers=[n])
    out = apply_snapshot(db, m, "Shoe\nUpdated 9 minutes ago", None, now=T0 + timedelta(hours=1), notifiers=[n])
    assert out.kind == "unchanged"
    assert n.events == []


def test_real_change_is_stored_and_notified_once(db):
    m, n = make_monitor(db), FakeNotifier()
    apply_snapshot(db, m, PAGE_A, None, now=T0, notifiers=[n])
    out = apply_snapshot(db, m, PAGE_B, None, now=T0 + timedelta(hours=1), notifiers=[n])
    assert out.kind == "changed" and out.notified
    assert len(n.events) == 1
    row = changes(db)[0]
    assert row.modified_count == 1 and "$12.00" in row.summary
    assert m.unseen_changes == 1

    # Checking the same content again must not notify again
    apply_snapshot(db, m, PAGE_B, None, now=T0 + timedelta(hours=2), notifiers=[n])
    assert len(n.events) == 1 and len(changes(db)) == 1


def test_flip_flopping_content_does_not_spam(db):
    m, n = make_monitor(db), FakeNotifier()
    apply_snapshot(db, m, PAGE_A, None, now=T0, notifiers=[n])
    apply_snapshot(db, m, PAGE_B, None, now=T0 + timedelta(hours=1), notifiers=[n])  # A->B notified
    apply_snapshot(db, m, PAGE_A, None, now=T0 + timedelta(hours=2), notifiers=[n])  # B->A notified
    apply_snapshot(db, m, PAGE_B, None, now=T0 + timedelta(hours=3), notifiers=[n])  # A->B again: suppressed
    assert len(n.events) == 2
    rows = changes(db)
    assert len(rows) == 3  # still recorded in history
    assert rows[-1].notified is False
    assert "already reported" in rows[-1].notification_note


def test_repeat_is_reported_again_after_dedup_window(db):
    m, n = make_monitor(db), FakeNotifier()
    apply_snapshot(db, m, PAGE_A, None, now=T0, notifiers=[n])
    apply_snapshot(db, m, PAGE_B, None, now=T0 + timedelta(hours=1), notifiers=[n])
    apply_snapshot(db, m, PAGE_A, None, now=T0 + timedelta(hours=2), notifiers=[n])
    apply_snapshot(db, m, PAGE_B, None, now=T0 + timedelta(days=3), notifiers=[n])
    assert len(n.events) == 3


def test_failed_notification_is_retried_on_next_identical_change(db):
    class Flaky(FakeNotifier):
        fail = True

        def send(self, event):
            if self.fail:
                from app.notifications.base import NotificationError

                raise NotificationError("down")
            super().send(event)

    m, n = make_monitor(db), Flaky()
    apply_snapshot(db, m, PAGE_A, None, now=T0, notifiers=[n])
    apply_snapshot(db, m, PAGE_B, None, now=T0 + timedelta(hours=1), notifiers=[n])
    assert changes(db)[0].notified is False and "down" in changes(db)[0].notification_note
    # Not marked notified, so it isn't treated as a duplicate later
    n.fail = False
    apply_snapshot(db, m, PAGE_A, None, now=T0 + timedelta(hours=2), notifiers=[n])
    apply_snapshot(db, m, PAGE_B, None, now=T0 + timedelta(hours=3), notifiers=[n])
    assert len(n.events) == 2  # B->A and the retried A->B


def test_focus_filter_ignores_irrelevant_changes_but_moves_baseline(db):
    m, n = make_monitor(db, focus="price"), FakeNotifier()
    apply_snapshot(db, m, "Shoe\nPrice: $10.00\nFooter v1", None, now=T0, notifiers=[n])
    out = apply_snapshot(db, m, "Shoe\nPrice: $10.00\nA completely different footer", None, now=T0 + timedelta(hours=1), notifiers=[n])
    assert out.kind == "ignored"
    assert changes(db) == [] and n.events == []
    out = apply_snapshot(db, m, "Shoe\nPrice: $9.00\nA completely different footer", None, now=T0 + timedelta(hours=2), notifiers=[n])
    assert out.kind == "changed"
    assert len(n.events) == 1


def test_notifications_can_be_disabled(db):
    m = make_monitor(db, notify_discord=False)
    apply_snapshot(db, m, PAGE_A, None, now=T0, notifiers=[])
    out = apply_snapshot(db, m, PAGE_B, None, now=T0 + timedelta(hours=1), notifiers=[])
    assert out.kind == "changed" and out.notified is False
    assert len(changes(db)) == 1


def test_failures_set_error_state_and_alert_once(db):
    m, n = make_monitor(db, notify_on_error=True), FakeNotifier()
    for i in range(5):
        apply_failure(db, m, "The site responded with HTTP 503.", now=T0 + timedelta(hours=i), notifiers=[n])
    assert m.last_result == "error" and m.consecutive_failures == 5
    assert len(n.events) == 1 and n.events[0].kind == "error"


def test_success_after_failure_clears_error(db):
    m, n = make_monitor(db), FakeNotifier()
    apply_failure(db, m, "boom", now=T0, notifiers=[n])
    apply_snapshot(db, m, PAGE_A, None, now=T0 + timedelta(hours=1), notifiers=[n])
    assert m.last_result == "ok" and m.last_error is None and m.consecutive_failures == 0