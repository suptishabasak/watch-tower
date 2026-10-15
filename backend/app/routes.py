import logging
import json
from datetime import timedelta
from xml.etree.ElementTree import Element, SubElement, tostring

from fastapi.responses import Response

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .config import get_settings
from .database import get_db
from .demo import clear_demo, seed_demo
from .diffing import compare_text, serialize_diff
from .models import Change, Monitor, Snapshot, utcnow
from .fetcher import FetchError, fetch_preview_html
from .notifications import ChangeEvent, build_notifiers, dispatch
from .scheduler import enqueue_check
from .schemas import INTERVALS, MonitorCreate, MonitorUpdate
from .security import UnsafeURLError, validate_public_url
from .serializers import serialize_change, serialize_monitor, serialize_snapshot
from .storage import delete_screenshots

logger = logging.getLogger(__name__)
router = APIRouter()
settings = get_settings()


def _get(db: Session, monitor_id: int) -> Monitor:
    m = db.get(Monitor, monitor_id)
    if m is None:
        raise HTTPException(404, "That monitor no longer exists.")
    return m


def _validated_url(raw: str) -> str:
    try:
        return validate_public_url(raw)
    except UnsafeURLError as exc:
        raise HTTPException(422, str(exc)) from None


@router.get("/health")
def health():
    return {"status": "ok"}


@router.post("/region-preview")
def region_preview(payload: dict):
    raw_url = payload.get("url", "")
    url = _validated_url(raw_url)
    try:
        result = fetch_preview_html(url, timeout_s=settings.page_timeout_seconds,
                                    user_agent=settings.user_agent,
                                    no_sandbox=settings.playwright_no_sandbox)
        return result
    except FetchError as exc:
        raise HTTPException(422, str(exc)) from None


@router.get("/config")
def get_config():
    # Booleans only; the webhook itself never leaves the server
    return {
        "discord_configured": bool(settings.discord_webhook_url),
        "email_configured": bool(settings.email_enabled and settings.smtp_host and settings.smtp_from and settings.smtp_to),
        "telegram_configured": bool(settings.telegram_bot_token and settings.telegram_chat_id),
        "digest_enabled": bool(settings.daily_digest_enabled),
        "demo_mode": settings.demo_mode,
        "scheduler_enabled": settings.scheduler_enabled,
        "intervals": list(INTERVALS),
    }


@router.get("/monitors")
def list_monitors(db: Session = Depends(get_db)):
    counts = dict(db.execute(select(Change.monitor_id, func.count()).group_by(Change.monitor_id)).all())
    monitors = db.scalars(select(Monitor).order_by(Monitor.created_at.desc())).all()
    return [serialize_monitor(m, counts.get(m.id, 0)) for m in monitors]


@router.post("/monitors", status_code=201)
def create_monitor(payload: MonitorCreate, db: Session = Depends(get_db)):
    url = _validated_url(payload.url)
    m = Monitor(
        name=payload.name,
        url=url,
        interval_minutes=payload.interval_minutes,
        focus=payload.focus,
        sensitivity=payload.sensitivity,
        watch_selectors=json.dumps(payload.watch_selectors),
        ignore_selectors=json.dumps(payload.ignore_selectors),
        notify_discord=payload.notify_discord,
        notify_email=payload.notify_email,
        notify_telegram=payload.notify_telegram,
        notify_on_error=payload.notify_on_error,
        discord_webhook_url=payload.discord_webhook_url or None,
        next_check_at=utcnow(),
    )
    db.add(m)
    db.commit()
    db.refresh(m)
    enqueue_check(m.id)  # first check stores the baseline right away
    db.refresh(m)
    return serialize_monitor(m, 0)


@router.get("/monitors/{monitor_id}")
def get_monitor(monitor_id: int, db: Session = Depends(get_db)):
    m = _get(db, monitor_id)
    count = db.scalar(select(func.count()).select_from(Change).where(Change.monitor_id == m.id)) or 0
    return serialize_monitor(m, count)


@router.patch("/monitors/{monitor_id}")
def update_monitor(monitor_id: int, payload: MonitorUpdate, db: Session = Depends(get_db)):
    m = _get(db, monitor_id)
    data = payload.model_dump(exclude_unset=True)
    now = utcnow()
    url_changed = False

    if data.get("url"):
        new_url = _validated_url(data["url"])
        if new_url != m.url:
            m.url = new_url
            m.last_hash = None  # different page: start a fresh baseline
            m.last_text = None
            m.unseen_changes = 0
            m.last_result = "pending"
            m.last_error = None
            m.consecutive_failures = 0
            m.next_check_at = now
            url_changed = True

    if data.get("name"):
        m.name = data["name"]
    if "focus" in data:
        m.focus = data["focus"]
    if data.get("sensitivity") is not None:
        m.sensitivity = data["sensitivity"]
    if data.get("watch_selectors") is not None:
        m.watch_selectors = json.dumps(data["watch_selectors"])
    if data.get("ignore_selectors") is not None:
        m.ignore_selectors = json.dumps(data["ignore_selectors"])
    if data.get("notify_discord") is not None:
        m.notify_discord = data["notify_discord"]
    if data.get("notify_email") is not None:
        m.notify_email = data["notify_email"]
    if data.get("notify_telegram") is not None:
        m.notify_telegram = data["notify_telegram"]
    if data.get("notify_on_error") is not None:
        m.notify_on_error = data["notify_on_error"]
    if "discord_webhook_url" in data and data["discord_webhook_url"] is not None:
        m.discord_webhook_url = data["discord_webhook_url"] or None
    if data.get("interval_minutes") and data["interval_minutes"] != m.interval_minutes:
        m.interval_minutes = data["interval_minutes"]
        m.next_check_at = (m.last_checked_at or now) + timedelta(minutes=m.interval_minutes)

    db.commit()
    if url_changed and not m.paused and not m.is_demo:
        enqueue_check(m.id)
    db.refresh(m)
    count = db.scalar(select(func.count()).select_from(Change).where(Change.monitor_id == m.id)) or 0
    return serialize_monitor(m, count)


@router.delete("/monitors/{monitor_id}", status_code=204)
def delete_monitor(monitor_id: int, db: Session = Depends(get_db)):
    m = _get(db, monitor_id)
    names = [m.last_screenshot]
    for c in m.changes:
        names += [c.before_screenshot, c.after_screenshot]
    names += [snap.screenshot for snap in m.snapshots]
    db.delete(m)
    db.commit()
    delete_screenshots(names)


@router.post("/monitors/{monitor_id}/check", status_code=202)
def check_now(monitor_id: int, db: Session = Depends(get_db)):
    _get(db, monitor_id)
    if not enqueue_check(monitor_id):
        raise HTTPException(409, "A check is already running for this monitor.")
    return {"queued": True}


@router.post("/monitors/{monitor_id}/pause")
def pause_monitor(monitor_id: int, db: Session = Depends(get_db)):
    m = _get(db, monitor_id)
    m.paused = True
    db.commit()
    return serialize_monitor(m)


@router.post("/monitors/{monitor_id}/resume")
def resume_monitor(monitor_id: int, db: Session = Depends(get_db)):
    m = _get(db, monitor_id)
    m.paused = False
    m.next_check_at = utcnow()  # check right away on resume
    db.commit()
    return serialize_monitor(m)


@router.post("/monitors/{monitor_id}/seen")
def mark_seen(monitor_id: int, db: Session = Depends(get_db)):
    m = _get(db, monitor_id)
    m.unseen_changes = 0
    db.commit()
    return serialize_monitor(m)


@router.get("/monitors/{monitor_id}/changes")
def list_changes(monitor_id: int, limit: int = Query(50, ge=1, le=200), db: Session = Depends(get_db)):
    _get(db, monitor_id)
    rows = db.scalars(
        select(Change)
        .where(Change.monitor_id == monitor_id)
        .order_by(Change.detected_at.desc(), Change.id.desc())
        .limit(limit)
    ).all()
    return [serialize_change(c) for c in rows]


def _snapshot(db: Session, monitor_id: int, snapshot_id: int) -> Snapshot:
    snap = db.get(Snapshot, snapshot_id)
    if snap is None or snap.monitor_id != monitor_id:
        raise HTTPException(404, "That saved version no longer exists.")
    return snap


@router.get("/monitors/{monitor_id}/snapshots")
def list_snapshots(monitor_id: int, limit: int = Query(100, ge=1, le=200), db: Session = Depends(get_db)):
    """Version timeline: one entry per stored version of the page, newest first (text not included)."""
    _get(db, monitor_id)
    rows = db.scalars(
        select(Snapshot)
        .where(Snapshot.monitor_id == monitor_id)
        .order_by(Snapshot.created_at.desc(), Snapshot.id.desc())
        .limit(limit)
    ).all()
    return [serialize_snapshot(x) for x in rows]


@router.get("/monitors/{monitor_id}/snapshots/{snapshot_id}")
def get_snapshot(monitor_id: int, snapshot_id: int, db: Session = Depends(get_db)):
    _get(db, monitor_id)
    return serialize_snapshot(_snapshot(db, monitor_id, snapshot_id), include_text=True)


@router.get("/monitors/{monitor_id}/compare")
def compare_versions(monitor_id: int, a: int, b: int, db: Session = Depends(get_db)):
    """Text diff between any two stored versions. The older one is always treated as 'before'."""
    _get(db, monitor_id)
    sa, sb = _snapshot(db, monitor_id, a), _snapshot(db, monitor_id, b)
    if (sa.created_at, sa.id) > (sb.created_at, sb.id):
        sa, sb = sb, sa
    result = compare_text((sa.text or "").split("\n"), (sb.text or "").split("\n"))
    diff = json.loads(serialize_diff(result))
    return {
        "before": serialize_snapshot(sa),
        "after": serialize_snapshot(sb),
        "counts": result.counts,
        "changes": diff["items"],
        "omitted": diff["omitted"],
    }


@router.post("/monitors/{monitor_id}/test-notification")
def test_notification(monitor_id: int, db: Session = Depends(get_db)):
    m = _get(db, monitor_id)
    notifiers = build_notifiers(m, settings, force=True)
    if not notifiers:
        raise HTTPException(
            400, "No Discord webhook is set. Add one to this monitor or set DISCORD_WEBHOOK_URL on the server."
        )
    event = ChangeEvent(
        kind="test",
        monitor_name=m.name,
        url=m.url,
        detected_at=utcnow(),
        summary="This is a test message from Watchtower. Notifications for this monitor are working.",
        dashboard_url=settings.public_dashboard_url or None,
    )
    sent, note = dispatch(notifiers, event)
    if not sent:
        raise HTTPException(502, note or "The test message could not be sent.")
    return {"sent": True}




@router.get("/digest")
def get_digest(hours: int = Query(24, ge=1, le=168), db: Session = Depends(get_db)):
    """Return a ready-to-render digest of recent changes; safe to schedule externally."""
    cutoff = utcnow() - timedelta(hours=hours)
    rows = db.scalars(select(Change).where(Change.detected_at >= cutoff)
                      .order_by(Change.detected_at.desc()).limit(500)).all()
    return {
        "period_hours": hours,
        "count": len(rows),
        "items": [{
            "monitor_id": c.monitor_id,
            "monitor_name": c.monitor.name if c.monitor else "Deleted monitor",
            "url": c.monitor.url if c.monitor else "",
            "detected_at": c.detected_at.isoformat() + "Z",
            "summary": c.summary,
        } for c in rows],
    }

@router.post("/demo/seed", status_code=201)
def seed(db: Session = Depends(get_db)):
    return {"created": seed_demo(db)}


@router.delete("/demo", status_code=204)
def remove_demo(db: Session = Depends(get_db)):
    clear_demo(db)

@router.get("/monitors/{monitor_id}/feed.xml")
def monitor_feed(monitor_id: int, db: Session = Depends(get_db)):
    """RSS 2.0 feed for the recent changes of one monitor."""
    monitor = _get(db, monitor_id)
    rows = db.scalars(
        select(Change).where(Change.monitor_id == monitor_id)
        .order_by(Change.detected_at.desc(), Change.id.desc()).limit(50)
    ).all()
    root = Element("rss", version="2.0")
    channel = SubElement(root, "channel")
    SubElement(channel, "title").text = f"Watchtower: {monitor.name}"
    SubElement(channel, "link").text = monitor.url
    SubElement(channel, "description").text = f"Recent detected changes for {monitor.name}"
    for change in rows:
        item = SubElement(channel, "item")
        SubElement(item, "title").text = change.summary[:200]
        SubElement(item, "link").text = monitor.url
        SubElement(item, "guid", isPermaLink="false").text = f"watchtower-change-{change.id}"
        SubElement(item, "pubDate").text = change.detected_at.strftime("%a, %d %b %Y %H:%M:%S +0000")
        SubElement(item, "description").text = change.summary
    return Response(content=tostring(root, encoding="utf-8", xml_declaration=True),
                    media_type="application/rss+xml; charset=utf-8")
