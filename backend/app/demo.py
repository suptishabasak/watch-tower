"""Sample data so the dashboard is usable without Playwright or internet access."""
import random
import re
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from .checker import apply_snapshot
from .diffing import change_key, compare_text, fingerprint, normalize_text, serialize_diff, summarize
from .models import Change, Monitor, utcnow
from .storage import delete_screenshots


def _shoe(price: str, stock: str = "In stock") -> str:
    return "\n".join(
        [
            "Aerolite Trail Runner",
            "Free shipping on orders over $75",
            f"Price: {price}",
            f"Availability: {stock}",
            "Sizes: 7, 8, 9, 10, 11",
            "Rated 4.6 out of 5 from 212 reviews",
        ]
    )


NEWS_BASE = "\n".join(
    [
        "City Library Announcements",
        "Summer reading program registration opens June 1.",
        "Teen robotics club meets Thursdays at 4 PM.",
        "Free tax help available through April 15.",
    ]
)
NEWS_NEW = NEWS_BASE + "\nNotice: Central branch closed Monday for maintenance."

RESULTS = "\n".join(
    [
        "Spring Regatta Results",
        "Division A: Harbor Club 1st, Bayview 2nd",
        "Division B: Northpoint 1st, Eastside 2nd",
        "Final standings will be posted after the protest window closes.",
    ]
)


def _set_baseline(m: Monitor, text: str) -> None:
    lines = normalize_text(text)
    m.last_text = "\n".join(lines)
    m.last_hash = fingerprint(lines)


def _add_change(db: Session, m: Monitor, before: str, after: str, when, notified: bool) -> None:
    old, new = normalize_text(before), normalize_text(after)
    result = compare_text(old, new, m.focus)
    if not result.significant:
        return
    db.add(
        Change(
            monitor_id=m.id,
            detected_at=when,
            summary=summarize(result),
            added_count=result.counts["added"],
            removed_count=result.counts["removed"],
            modified_count=result.counts["modified"],
            diff_json=serialize_diff(result),
            change_key=change_key(fingerprint(old), fingerprint(new)),
            notified=notified,
            notification_note=None if notified else "Demo data: no notification was sent.",
        )
    )


def seed_demo(db: Session) -> int:
    now = utcnow()
    shoe = Monitor(
        name="Aerolite Trail Runner",
        url="https://shop.example.com/aerolite",
        interval_minutes=60,
        focus="price, availability",
        is_demo=True,
        last_result="ok",
        created_at=now - timedelta(days=6),
        last_checked_at=now - timedelta(minutes=18),
        next_check_at=now + timedelta(minutes=42),
        last_changed_at=now - timedelta(hours=5),
        unseen_changes=1,
    )
    news = Monitor(
        name="City Library announcements",
        url="https://library.example.org/news",
        interval_minutes=360,
        is_demo=True,
        last_result="ok",
        created_at=now - timedelta(days=9),
        last_checked_at=now - timedelta(hours=2),
        next_check_at=now + timedelta(hours=4),
        last_changed_at=now - timedelta(days=2),
    )
    results = Monitor(
        name="Regatta results",
        url="https://regatta.example.net/results",
        interval_minutes=1440,
        is_demo=True,
        last_result="error",
        last_error="The site responded with HTTP 503.",
        consecutive_failures=2,
        created_at=now - timedelta(days=3),
        last_checked_at=now - timedelta(hours=7),
        next_check_at=now + timedelta(hours=17),
    )
    docs = Monitor(
        name="Framework changelog",
        url="https://docs.example.dev/changelog",
        interval_minutes=15,
        is_demo=True,
        paused=True,
        last_result="ok",
        created_at=now - timedelta(days=12),
        last_checked_at=now - timedelta(days=1),
    )
    _set_baseline(shoe, _shoe("$109.00", "Only 3 left"))
    _set_baseline(news, NEWS_NEW)
    _set_baseline(results, RESULTS)
    _set_baseline(docs, "Changelog\nv2.4.1 Fixed a bug in the router.")
    db.add_all([shoe, news, results, docs])
    db.flush()

    _add_change(db, shoe, _shoe("$129.00"), _shoe("$119.00"), now - timedelta(days=3), True)
    _add_change(db, shoe, _shoe("$119.00"), _shoe("$109.00", "Only 3 left"), now - timedelta(hours=5), True)
    _add_change(db, news, NEWS_BASE, NEWS_NEW, now - timedelta(days=2), True)
    db.commit()
    return 4


def seed_demo_if_empty(db: Session) -> None:
    if db.scalar(select(Monitor.id).limit(1)) is None:
        seed_demo(db)


def clear_demo(db: Session) -> None:
    for m in db.scalars(select(Monitor).where(Monitor.is_demo.is_(True))).all():
        delete_screenshots([m.last_screenshot, *[n for c in m.changes for n in (c.before_screenshot, c.after_screenshot)],
                           *[snap.screenshot for snap in m.snapshots]])
        db.delete(m)
    db.commit()


def simulate_check(db: Session, monitor: Monitor) -> None:
    """Pretend the page changed, then run the normal pipeline (no browser, no notifications)."""
    current = monitor.last_text or ""
    match = re.search(r"\$\d+\.\d{2}", current)
    if match:
        old_price = match.group(0)
        new_price = old_price
        while new_price == old_price:
            new_price = f"${random.randint(8900, 13900) / 100:.2f}"
        new_text = current.replace(old_price, new_price, 1)
    else:
        new_text = current + f"\nNotice #{random.randint(100, 999)}: Schedule update posted for this weekend."
    apply_snapshot(db, monitor, new_text, None, notifiers=[])