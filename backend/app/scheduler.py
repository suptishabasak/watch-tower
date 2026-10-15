import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy import select, update

from .checker import run_check
from .config import get_settings
from .database import SessionLocal
from .models import Monitor, utcnow

logger = logging.getLogger(__name__)
settings = get_settings()

_executor: ThreadPoolExecutor | None = None
_scheduler: BackgroundScheduler | None = None
_lock = threading.Lock()


def _get_executor() -> ThreadPoolExecutor:
    global _executor
    with _lock:
        if _executor is None:
            _executor = ThreadPoolExecutor(
                max_workers=settings.max_concurrent_checks, thread_name_prefix="watchtower-check"
            )
        return _executor


def enqueue_check(monitor_id: int) -> bool:
    """Queue a check. Returns False if one is already queued/running for this monitor."""
    with SessionLocal() as db:
        # Atomic claim: only one caller can flip checking False -> True
        result = db.execute(
            update(Monitor).where(Monitor.id == monitor_id, Monitor.checking.is_(False)).values(checking=True)
        )
        db.commit()
        if result.rowcount == 0:
            return False
    _get_executor().submit(_safe_run, monitor_id)
    return True


def _safe_run(monitor_id: int) -> None:
    try:
        run_check(monitor_id)
    except Exception:
        logger.exception("Unhandled error in check worker for monitor %s", monitor_id)


def tick() -> None:
    with SessionLocal() as db:
        due = db.scalars(
            select(Monitor.id).where(
                Monitor.paused.is_(False),
                Monitor.checking.is_(False),
                Monitor.is_demo.is_(False),
                Monitor.next_check_at <= utcnow(),
            )
        ).all()
    for monitor_id in due:
        enqueue_check(monitor_id)


def reset_stale_checks() -> None:
    """A crash or restart can leave monitors stuck in 'checking'."""
    with SessionLocal() as db:
        db.execute(update(Monitor).values(checking=False))
        db.commit()


def start_scheduler() -> None:
    global _scheduler
    _scheduler = BackgroundScheduler(timezone="UTC")
    _scheduler.add_job(
        tick,
        "interval",
        seconds=settings.scheduler_tick_seconds,
        id="tick",
        max_instances=1,
        coalesce=True,
        next_run_time=datetime.now(timezone.utc),
    )
    _scheduler.start()
    logger.info("Scheduler started (tick every %ss)", settings.scheduler_tick_seconds)


def stop_scheduler() -> None:
    global _scheduler, _executor
    if _scheduler:
        _scheduler.shutdown(wait=False)
        _scheduler = None
    if _executor:
        _executor.shutdown(wait=False, cancel_futures=True)
        _executor = None