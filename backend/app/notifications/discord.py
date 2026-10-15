from datetime import timezone
import re, time, httpx
from .base import ChangeEvent, NotificationError

def is_valid_webhook_url(value: str) -> bool:
    return bool(value and re.fullmatch(r"https://(?:discord\.com|discordapp\.com)/api/webhooks/\d+/[A-Za-z0-9._-]+/?", value))

def format_discord_payload(event: ChangeEvent) -> dict:
    when = event.detected_at
    if when.tzinfo is None: when = when.replace(tzinfo=timezone.utc)
    title = {"error":"Watchtower page failing", "test":"Watchtower Test", "change":"Watchtower detected a change"}.get(event.kind, "Watchtower update")
    fields = [{"name":"Website","value":event.url[:1024],"inline":False},{"name":"Detected","value":f"<t:{int(when.timestamp())}:f>","inline":True}]
    if event.changes:
        rows = [f"- {str(x.get('before') or '∅')[:150]}\n+ {str(x.get('after') or '∅')[:150]}" for x in event.changes[:5]]
        fields.append({"name":"What changed","value":"```diff\n"+"\n".join(rows).replace("```","'''")[:900]+"\n```","inline":False})
    if event.dashboard_url: fields.append({"name":"Dashboard","value":event.dashboard_url[:1024],"inline":False})
    return {"embeds":[{"title":f"{title}: {event.monitor_name}"[:256],"url":event.url,"description":event.summary[:3000],"fields":fields,"timestamp":when.isoformat()}],"allowed_mentions":{"parse":[]}}

class DiscordNotifier:
    name = "Discord"
    def __init__(self, webhook_url: str, client=None, timeout: float = 8.0):
        if not is_valid_webhook_url(webhook_url): raise NotificationError("Invalid Discord webhook URL.")
        self._url, self.client, self.timeout = webhook_url, client, timeout

    def send(self, event: ChangeEvent) -> None:
        when = event.detected_at
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
        lines = [f"**Watchtower · {event.kind.title()}**", f"**{event.monitor_name}**", event.summary[:1200], f"[Open monitored page]({event.url})", f"Detected: {when.astimezone(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}"]
        if event.dashboard_url:
            lines.append(f"[Open Watchtower dashboard]({event.dashboard_url})")
        for item in event.changes[:5]:
            lines.append(f"• {item.get('kind', 'change')}: `{str(item.get('before') or '∅')[:100]}` → `{str(item.get('after') or '∅')[:100]}`")
        own = self.client is None
        client = self.client or httpx.Client(timeout=self.timeout)
        try:
            for attempt in range(2):
                response = client.post(self._url, json=format_discord_payload(event), timeout=self.timeout)
                if response.status_code == 429 and attempt == 0:
                    try: time.sleep(min(float(response.json().get("retry_after", .5)), 2))
                    except Exception: time.sleep(.5)
                    continue
                if response.status_code >= 400: raise NotificationError(f"Discord returned HTTP {response.status_code}.")
                return
        except NotificationError: raise
        except Exception as exc: raise NotificationError(f"Discord delivery failed ({type(exc).__name__}).") from None
        finally:
            if own: client.close()

def build_notifiers(monitor, settings, force: bool = False):
    if not force and not getattr(monitor, "notify_discord", False):
        return []
    url = getattr(monitor, "discord_webhook_url", None) or getattr(settings, "discord_webhook_url", "")
    if not url:
        return []
    return [DiscordNotifier(url)] if is_valid_webhook_url(url) else []
