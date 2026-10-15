"""The check pipeline: fetch -> normalise -> compare -> store -> (maybe) notify."""
from __future__ import annotations

import logging
import time
import json
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from .config import get_settings
from .database import SessionLocal
from .diffing import (
    change_key,
    compare_text,
    fingerprint,
    normalize_text,
    relevant_changes,
    serialize_diff,
    summarize,
)
from .fetcher import FetchError, fetch_page
from .models import Change, Monitor, Snapshot, utcnow
from .notifications import ChangeEvent, Notifier, build_notifiers, dispatch
from .security import UnsafeURLError
from .storage import delete_screenshots, save_screenshot

logger = logging.getLogger(__name__)
settings = get_settings()

FAILURES_BEFORE_ALERT = 3


@dataclass
class CheckOutcome:
    kind: str  # baseline | unchanged | ignored | changed | failed
    change_id: int | None = None
    notified: bool = False


def recently_notified(db: Session, monitor_id: int, key: str, now: datetime, hours: int) -> bool:
    cutoff = now - timedelta(hours=hours)
    count = db.scalar(
        select(func.count())
        .select_from(Change)
        .where(
            Change.monitor_id == monitor_id,
            Change.change_key == key,
            Change.notified.is_(True),
            Change.detected_at >= cutoff,
        )
    )
    return bool(count)


def record_snapshot(
    db: Session, monitor: Monitor, content_hash: str, text: str, screenshot: bytes | None, now: datetime
) -> Snapshot:
    """Persist one version of the page (text + screenshot). Called only when the content hash changed."""
    snap = Snapshot(
        monitor_id=monitor.id,
        created_at=now,
        content_hash=content_hash,
        text=text,
        screenshot=save_screenshot(monitor.id, screenshot),
    )
    db.add(snap)
    db.flush()
    return snap


def ensure_baseline_snapshot(db: Session, monitor: Monitor) -> None:
    """Monitors created before snapshots existed only have last_text; turn it into the first version."""
    if not monitor.last_hash or not monitor.last_text:
        return
    exists = db.scalar(
        select(func.count())
        .select_from(Snapshot)
        .where(Snapshot.monitor_id == monitor.id, Snapshot.content_hash == monitor.last_hash)
    )
    if exists:
        return
    db.add(
        Snapshot(
            monitor_id=monitor.id,
            created_at=monitor.last_changed_at or monitor.created_at or utcnow(),
            content_hash=monitor.last_hash,
            text=monitor.last_text,
            screenshot=monitor.last_screenshot,
        )
    )
    db.flush()


def prune_history(db: Session, monitor: Monitor, keep: int) -> None:
    stale_changes = db.scalars(
        select(Change)
        .where(Change.monitor_id == monitor.id)
        .order_by(Change.detected_at.desc(), Change.id.desc())
        .offset(keep)
    ).all()
    stale_snaps = db.scalars(
        select(Snapshot)
        .where(Snapshot.monitor_id == monitor.id)
        .order_by(Snapshot.created_at.desc(), Snapshot.id.desc())
        .offset(keep + 1)  # `keep` changes span keep + 1 versions
    ).all()
    if not stale_changes and not stale_snaps:
        return
    candidates = {n for c in stale_changes for n in (c.before_screenshot, c.after_screenshot) if n}
    candidates |= {x.screenshot for x in stale_snaps if x.screenshot}
    for row in (*stale_changes, *stale_snaps):
        db.delete(row)
    db.commit()
    kept = {n for c in db.scalars(select(Change).where(Change.monitor_id == monitor.id)).all()
            for n in (c.before_screenshot, c.after_screenshot) if n}
    kept |= {x.screenshot for x in db.scalars(select(Snapshot).where(Snapshot.monitor_id == monitor.id)).all()
             if x.screenshot}
    if monitor.last_screenshot:
        kept.add(monitor.last_screenshot)
    delete_screenshots(candidates - kept)


def apply_snapshot(
    db: Session,
    monitor: Monitor,
    raw_text: str,
    screenshot: bytes | None,
    *,
    now: datetime | None = None,
    notifiers: list[Notifier] | None = None,
) -> CheckOutcome:
    now = now or utcnow()
    lines = normalize_text(raw_text)
    if not lines:
        return apply_failure(db, monitor, "The page had no readable text after cleanup.", now=now, notifiers=notifiers)

    new_hash = fingerprint(lines)
    monitor.last_checked_at = now
    monitor.next_check_at = now + timedelta(minutes=monitor.interval_minutes)
    monitor.last_result = "ok"
    monitor.last_error = None
    monitor.consecutive_failures = 0
    monitor.error_notified = False

    # First successful check: store the baseline, don't report a "change"
    if monitor.last_hash is None:
        monitor.last_hash = new_hash
        monitor.last_text = "\n".join(lines)
        snap = record_snapshot(db, monitor, new_hash, monitor.last_text, screenshot, now)
        monitor.last_screenshot = snap.screenshot
        db.commit()
        return CheckOutcome("baseline")

    if new_hash == monitor.last_hash:
        db.commit()
        return CheckOutcome("unchanged")

    ensure_baseline_snapshot(db, monitor)
    old_lines = (monitor.last_text or "").split("\n")
    prev_hash = monitor.last_hash
    prev_screenshot = monitor.last_screenshot
    result = compare_text(old_lines, lines, monitor.focus)
    # Sensitivity 1 = strict (more small changes), 2 = balanced, 3 = high signal.
    if monitor.sensitivity == 1:
        result.significant = bool(result.counts["added"] + result.counts["removed"] + result.counts["modified"])
    elif monitor.sensitivity == 3:
        total = max(1, len(old_lines))
        delta = result.counts["added"] + result.counts["removed"] + result.counts["modified"]
        result.significant = result.significant and (delta >= 3 or delta / total >= 0.03)

    # Always move the baseline forward, so a change we ignore is not re-detected on every check
    monitor.last_hash = new_hash
    monitor.last_text = "\n".join(lines)

    # The hash changed, so this is a new version: store its text + screenshot even when the change is too
    # minor to alert on. That keeps the version timeline and "compare any two versions" complete.
    snap = record_snapshot(db, monitor, new_hash, monitor.last_text, screenshot, now)
    if snap.screenshot:
        monitor.last_screenshot = snap.screenshot

    if not result.significant:
        db.commit()
        return CheckOutcome("ignored")

    new_screenshot = snap.screenshot

    key = change_key(prev_hash, new_hash)
    suppressed = recently_notified(db, monitor.id, key, now, settings.notify_dedup_hours)
    summary = summarize(result)

    change = Change(
        monitor_id=monitor.id,
        detected_at=now,
        summary=summary,
        added_count=result.counts["added"],
        removed_count=result.counts["removed"],
        modified_count=result.counts["modified"],
        diff_json=serialize_diff(result),
        before_screenshot=prev_screenshot,
        after_screenshot=new_screenshot,
        change_key=key,
    )
    db.add(change)
    monitor.last_changed_at = now
    monitor.unseen_changes += 1
    db.commit()

    active = notifiers if notifiers is not None else build_notifiers(monitor, settings)
    if suppressed:
        change.notification_note = "Not sent: the same change was already reported recently."
    elif active:
        event = ChangeEvent(
            kind="change",
            monitor_name=monitor.name,
            url=monitor.url,
            detected_at=now,
            summary=summary,
            changes=[
                {"kind": c.kind, "before": c.before, "after": c.after} for c in relevant_changes(result)[:5]
            ],
            dashboard_url=settings.public_dashboard_url or None,
        )
        change.notified, change.notification_note = dispatch(active, event)
    db.commit()

    prune_history(db, monitor, settings.max_history_per_monitor)
    return CheckOutcome("changed", change.id, change.notified)


def apply_failure(
    db: Session,
    monitor: Monitor,
    message: str,
    *,
    now: datetime | None = None,
    notifiers: list[Notifier] | None = None,
) -> CheckOutcome:
    now = now or utcnow()
    monitor.last_checked_at = now
    monitor.next_check_at = now + timedelta(minutes=monitor.interval_minutes)
    monitor.last_result = "error"
    monitor.last_error = message[:500]
    monitor.consecutive_failures += 1
    db.commit()

    if (
        monitor.notify_on_error
        and monitor.consecutive_failures >= FAILURES_BEFORE_ALERT
        and not monitor.error_notified
    ):
        active = notifiers if notifiers is not None else build_notifiers(monitor, settings)
        if active:
            event = ChangeEvent(
                kind="error",
                monitor_name=monitor.name,
                url=monitor.url,
                detected_at=now,
                summary=f"The last {monitor.consecutive_failures} checks failed.\nLatest error: {message}",
                dashboard_url=settings.public_dashboard_url or None,
            )
            sent, _ = dispatch(active, event)
            monitor.error_notified = sent
            db.commit()
    return CheckOutcome("failed")


def run_check(monitor_id: int, *, fetcher=fetch_page) -> None:
    """Entry point used by worker threads. Never raises."""
    with SessionLocal() as db:
        try:
            monitor = db.get(Monitor, monitor_id)
            if monitor is None:
                return
            if monitor.is_demo:
                from .demo import simulate_check  # lazy: demo imports this module

                simulate_check(db, monitor)
                return
            try:
                snap = None
                last_error = None
                attempts = max(1, min(int(settings.fetch_retry_attempts), 5))
                for attempt in range(attempts):
                    try:
                        snap = fetcher(
                            monitor.url,
                            timeout_s=settings.page_timeout_seconds,
                            user_agent=settings.user_agent,
                            no_sandbox=settings.playwright_no_sandbox,
                            watch_selectors=json.loads(monitor.watch_selectors or "[]"),
                            ignore_selectors=json.loads(monitor.ignore_selectors or "[]"),
                            min_domain_interval_s=settings.domain_min_interval_seconds,
                            cache_seconds=settings.fetch_cache_seconds,
                        )
                        break
                    except (FetchError, UnsafeURLError) as exc:
                        last_error = exc
                        if isinstance(exc, UnsafeURLError) or attempt + 1 >= attempts:
                            break
                        time.sleep(min(2 ** attempt, 4))
                if snap is not None:
                    apply_snapshot(db, monitor, snap.text, snap.screenshot)
                elif isinstance(last_error, UnsafeURLError):
                    apply_failure(db, monitor, f"Blocked: {last_error}")
                else:
                    apply_failure(db, monitor, str(last_error or "Fetch failed."))
            except TypeError as exc:
                # Preserve compatibility with test/custom fetchers that do not accept throttling kwargs.
                if "unexpected keyword argument" not in str(exc):
                    raise
                snap = fetcher(monitor.url, timeout_s=settings.page_timeout_seconds,
                               user_agent=settings.user_agent, no_sandbox=settings.playwright_no_sandbox,
                               watch_selectors=json.loads(monitor.watch_selectors or "[]"),
                               ignore_selectors=json.loads(monitor.ignore_selectors or "[]"))
                apply_snapshot(db, monitor, snap.text, snap.screenshot)
        except Exception:
            logger.exception("Check crashed for monitor %s", monitor_id)
            try:
                db.rollback()
                monitor = db.get(Monitor, monitor_id)
                if monitor:
                    apply_failure(db, monitor, "Something went wrong while checking this page.")
            except Exception:
                logger.exception("Could not record failure for monitor %s", monitor_id)
        finally:
            db.rollback()
            db.execute(update(Monitor).where(Monitor.id == monitor_id).values(checking=False))
            db.commit()