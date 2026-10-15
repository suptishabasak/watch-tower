from dataclasses import dataclass, field
from datetime import datetime
import logging
from typing import Protocol
logger = logging.getLogger(__name__)

@dataclass
class ChangeEvent:
    kind: str
    monitor_name: str
    url: str
    detected_at: datetime
    summary: str
    changes: list[dict] = field(default_factory=list)
    dashboard_url: str | None = None

class NotificationError(RuntimeError):
    """Safe notification delivery error."""

class Notifier(Protocol):
    name: str
    def send(self, event: ChangeEvent) -> None: ...

def dispatch(notifiers: list[Notifier], event: ChangeEvent) -> tuple[bool, str | None]:
    if not notifiers:
        return False, None
    errors, sent = [], False
    for notifier in notifiers:
        try:
            notifier.send(event)
            sent = True
        except Exception as exc:
            logger.warning("%s notification failed: %s", getattr(notifier, "name", "Notifier"), exc)
            errors.append(f"{getattr(notifier, 'name', 'Notifier')}: {exc}")
    return sent, ("; ".join(errors)[:500] if errors else None)
