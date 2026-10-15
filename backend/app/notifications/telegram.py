import httpx
from .base import ChangeEvent, NotificationError

class TelegramNotifier:
    name = "Telegram"
    def __init__(self, token, chat_id, timeout=8):
        self.token, self.chat_id, self.timeout = token, chat_id, timeout
    def send(self, event: ChangeEvent) -> None:
        if not self.token or not self.chat_id:
            raise NotificationError("Telegram bot token or chat ID is missing.")
        text = f"Watchtower · {event.kind.title()}\n{event.monitor_name}\n{event.summary[:2200]}\n{event.url}"
        if event.dashboard_url:
            text += f"\n\nOpen dashboard: {event.dashboard_url}"
        try:
            response = httpx.post(f"https://api.telegram.org/bot{self.token}/sendMessage",
                                  json={"chat_id": self.chat_id, "text": text, "disable_web_page_preview": True},
                                  timeout=self.timeout)
            if response.status_code >= 400:
                raise NotificationError(f"Telegram returned HTTP {response.status_code}.")
            if not response.json().get("ok"):
                raise NotificationError("Telegram rejected the message.")
        except NotificationError:
            raise
        except Exception as exc:
            raise NotificationError(f"Telegram delivery failed ({type(exc).__name__}).") from None
