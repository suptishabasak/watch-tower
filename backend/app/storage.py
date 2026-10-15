import logging
import uuid
from collections.abc import Iterable
from pathlib import Path

from .config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


def save_screenshot(monitor_id: int, data: bytes | None) -> str | None:
    if not data:
        return None
    name = f"{monitor_id}-{uuid.uuid4().hex}.jpg"
    (settings.screenshots_dir / name).write_bytes(data)
    return name


def delete_screenshots(names: Iterable[str | None]) -> None:
    for name in {n for n in names if n}:
        try:
            (settings.screenshots_dir / Path(name).name).unlink(missing_ok=True)
        except OSError:
            logger.warning("Could not delete screenshot %s", name)