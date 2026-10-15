from datetime import datetime, timezone

import httpx
import pytest

import app.notifications.discord as discord_module
from app.notifications import build_notifiers, dispatch
from app.notifications.base import ChangeEvent, NotificationError, Notifier
from app.notifications.discord import DiscordNotifier, format_discord_payload, is_valid_webhook_url

WEBHOOK = "https://discord.com/api/webhooks/123456789012345678/abc-DEF_123"
WHEN = datetime(2026, 3, 1, 12, 0, 0, tzinfo=timezone.utc)


def make_event(**overrides):
    base = dict(
        kind="change",
        monitor_name="Acme Store",
        url="https://shop.example.com/item",
        detected_at=WHEN,
        summary="1 modified\n~ “Price: $10.00” → “Price: $12.00”",
        changes=[{"kind": "modified", "before": "Price: $10.00", "after": "Price: $12.00"}],
        dashboard_url="http://localhost:5173",
    )
    base.update(overrides)
    return ChangeEvent(**base)


def test_payload_contains_required_information():
    payload = format_discord_payload(make_event())
    embed = payload["embeds"][0]
    assert "Acme Store" in embed["title"]
    assert embed["url"] == "https://shop.example.com/item"
    assert "$12.00" in embed["description"]
    names = {f["name"]: f["value"] for f in embed["fields"]}
    assert names["Website"] == "https://shop.example.com/item"
    assert f"<t:{int(WHEN.timestamp())}:f>" in names["Detected"]
    assert "- Price: $10.00" in names["What changed"] and "+ Price: $12.00" in names["What changed"]
    assert names["Dashboard"] == "http://localhost:5173"
    assert embed["timestamp"].startswith("2026-03-01T12:00:00")


def test_payload_never_allows_mentions():
    event = make_event(summary="@everyone free stuff", monitor_name="@here")
    assert format_discord_payload(event)["allowed_mentions"] == {"parse": []}


def test_payload_respects_discord_limits():
    long = "x" * 5000
    event = make_event(
        monitor_name=long,
        url="https://example.com/" + long[:900],
        summary=long,
        changes=[{"kind": "added", "before": None, "after": long} for _ in range(20)],
    )
    embed = format_discord_payload(event)["embeds"][0]
    assert len(embed["title"]) <= 256
    assert len(embed["description"]) <= 4096
    assert all(len(f["value"]) <= 1024 for f in embed["fields"])
    total = len(embed["title"]) + len(embed["description"]) + sum(len(f["name"]) + len(f["value"]) for f in embed["fields"])
    assert total <= 6000


def test_code_fences_in_page_text_cannot_break_the_diff_block():
    event = make_event(changes=[{"kind": "added", "before": None, "after": "evil ``` break out"}])
    value = [f for f in format_discord_payload(event)["embeds"][0]["fields"] if f["name"] == "What changed"][0]["value"]
    assert value.count("```") == 2


def test_naive_datetimes_are_treated_as_utc():
    naive = datetime(2026, 3, 1, 12, 0, 0)
    payload = format_discord_payload(make_event(detected_at=naive))
    assert payload["embeds"][0]["timestamp"].endswith("+00:00")


def test_error_and_test_events_have_distinct_titles():
    assert "failing" in format_discord_payload(make_event(kind="error"))["embeds"][0]["title"]
    assert "Test" in format_discord_payload(make_event(kind="test"))["embeds"][0]["title"]


def test_webhook_url_validation():
    assert is_valid_webhook_url(WEBHOOK)
    assert not is_valid_webhook_url("http://discord.com/api/webhooks/1/abc")
    assert not is_valid_webhook_url("https://evil.com/api/webhooks/1/abc")
    assert not is_valid_webhook_url("https://discord.com.evil.com/api/webhooks/1/abc")
    assert not is_valid_webhook_url("http://169.254.169.254/")
    with pytest.raises(NotificationError):
        DiscordNotifier("https://evil.example.com/hook")


def _client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_discord_notifier_posts_payload():
    seen = {}

    def handler(request):
        seen["url"] = str(request.url)
        seen["json"] = request.read()
        return httpx.Response(204)

    DiscordNotifier(WEBHOOK, client=_client(handler)).send(make_event())
    assert seen["url"] == WEBHOOK
    assert b"Acme Store" in seen["json"]


def test_discord_notifier_retries_once_on_rate_limit(monkeypatch):
    monkeypatch.setattr(discord_module.time, "sleep", lambda _s: None)
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(429, json={"retry_after": 0.1}) if len(calls) == 1 else httpx.Response(204)

    DiscordNotifier(WEBHOOK, client=_client(handler)).send(make_event())
    assert len(calls) == 2


def test_discord_error_does_not_leak_webhook():
    def handler(request):
        return httpx.Response(401)

    with pytest.raises(NotificationError) as exc:
        DiscordNotifier(WEBHOOK, client=_client(handler)).send(make_event())
    assert "abc-DEF_123" not in str(exc.value)
    assert "401" in str(exc.value)


def test_network_error_does_not_leak_webhook():
    def handler(request):
        raise httpx.ConnectError("boom connecting to " + str(request.url))

    with pytest.raises(NotificationError) as exc:
        DiscordNotifier(WEBHOOK, client=_client(handler)).send(make_event())
    assert "abc-DEF_123" not in str(exc.value)


class _Ok(Notifier):
    name = "ok"

    def send(self, event):
        pass


class _Bad(Notifier):
    name = "bad"

    def send(self, event):
        raise NotificationError("nope")


def test_dispatch_reports_partial_failure():
    sent, note = dispatch([_Ok(), _Bad()], make_event())
    assert sent is True
    assert note == "bad: nope"
    assert dispatch([], make_event()) == (False, None)


class _Monitor:
    notify_discord = True
    discord_webhook_url = None


class _Settings:
    discord_webhook_url = ""


def test_build_notifiers_respects_preferences():
    m, s = _Monitor(), _Settings()
    assert build_notifiers(m, s) == []  # nothing configured
    s.discord_webhook_url = WEBHOOK
    assert len(build_notifiers(m, s)) == 1
    m.notify_discord = False
    assert build_notifiers(m, s) == []
    assert len(build_notifiers(m, s, force=True)) == 1
    m.discord_webhook_url = "https://discord.com/api/webhooks/999/zzz"
    assert build_notifiers(m, s, force=True)[0]._url.endswith("/999/zzz")  # per-monitor override wins