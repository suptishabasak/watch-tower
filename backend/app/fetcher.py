"""Playwright page extraction. Every request the browser makes (including redirects) is checked
against the SSRF rules in security.py before it is allowed to leave the machine."""
from __future__ import annotations

import logging
import time
import threading
import hashlib
from dataclasses import dataclass
from urllib.parse import urlsplit

from .security import UnsafeURLError, assert_public_host, validate_public_url

logger = logging.getLogger(__name__)

MAX_TEXT_CHARS = 200_000
_FETCH_LOCK = threading.RLock()
_DOMAIN_LAST_REQUEST: dict[str, float] = {}
_FETCH_CACHE: dict[str, tuple[float, PageSnapshot]] = {}

def _throttle_domain(url: str, minimum_interval: float) -> None:
    host = (urlsplit(url).hostname or "").lower()
    if not host or minimum_interval <= 0:
        return
    with _FETCH_LOCK:
        now = time.monotonic()
        wait = minimum_interval - (now - _DOMAIN_LAST_REQUEST.get(host, 0))
        if wait > 0:
            time.sleep(min(wait, 10))
        _DOMAIN_LAST_REQUEST[host] = time.monotonic()


class FetchError(Exception):
    """Expected failure with a user-presentable message."""


@dataclass
class PageSnapshot:
    final_url: str
    title: str
    text: str
    screenshot: bytes | None
    http_status: int
    preview_html: str = ""
    preview_styles: str = ""


EXTRACT_JS = """
(opts) => {
  const selectors = [
    'script','noscript','template','iframe','svg','canvas',
    'ins.adsbygoogle','[id^="google_ads"]','[class*="advert" i]','[id*="advert" i]',
    '[class*="sponsored" i]','[aria-label*="advertisement" i]','[data-ad-slot]','[data-ad]'
  ];
  document.querySelectorAll(selectors.join(',')).forEach(el => el.remove());
  const safeSelector = (s) => { try { return document.querySelectorAll(s); } catch { return []; } };
  (opts?.ignore || []).forEach(s => safeSelector(s).forEach(el => el.remove()));
  let text = '';
  const watch = opts?.watch || [];
  if (watch.length) {
    const chunks = [];
    watch.forEach(s => safeSelector(s).forEach(el => chunks.push(el.innerText || el.textContent || '')));
    text = chunks.join('\\n');
  } else {
    text = document.body ? document.body.innerText : '';
  }
  const clone = document.body ? document.body.cloneNode(true) : document.createElement('body');
  clone.querySelectorAll('script,noscript,template,iframe,object,embed,form,input,button,svg,canvas').forEach(el => el.remove());
  const sanitize = root => root.querySelectorAll('*').forEach(el => {
    [...el.attributes].forEach(a => { if (a.name.toLowerCase().startsWith('on') || a.name.toLowerCase() === 'srcdoc') el.removeAttribute(a.name); });
    el.removeAttribute('contenteditable');
  });
  sanitize(clone);
  const head = document.head ? document.head.cloneNode(true) : document.createElement('head');
  head.querySelectorAll('script,iframe,meta[http-equiv="refresh"]').forEach(el => el.remove());
  sanitize(head);
  return { title: document.title || '', text, html: clone.outerHTML, styles: head.innerHTML };
}
"""


def _request_allowed(url: str, cache: dict[str, bool]) -> bool:
    parts = urlsplit(url)
    scheme = parts.scheme.lower()
    if scheme in {"data", "blob", "about"}:
        return True
    if scheme not in {"http", "https", "ws", "wss"}:
        return False
    host = (parts.hostname or "").lower()
    if not host:
        return False
    if host not in cache:
        try:
            assert_public_host(host)
            cache[host] = True
        except UnsafeURLError:
            cache[host] = False
    return cache[host]


def _friendly_error(exc: Exception) -> str:
    msg = str(exc)
    mapping = [
        ("ERR_NAME_NOT_RESOLVED", "The domain name could not be found."),
        ("ERR_CONNECTION_REFUSED", "The server refused the connection."),
        ("ERR_CONNECTION_RESET", "The connection was reset by the server."),
        ("ERR_CONNECTION_TIMED_OUT", "The server took too long to respond."),
        ("ERR_TIMED_OUT", "The server took too long to respond."),
        ("ERR_CERT", "The site's TLS certificate is invalid."),
        ("ERR_SSL", "A TLS error occurred while connecting."),
        ("ERR_TOO_MANY_REDIRECTS", "The page redirected too many times."),
        ("ERR_BLOCKED_BY_CLIENT", "The page redirected to a blocked address."),
        ("ERR_INTERNET_DISCONNECTED", "The Watchtower server has no internet connection."),
    ]
    for needle, friendly in mapping:
        if needle in msg:
            return friendly
    first_line = msg.strip().splitlines()[0] if msg.strip() else type(exc).__name__
    return f"Browser error: {first_line[:160]}"


def fetch_page(url: str, *, timeout_s: int = 30, user_agent: str = "WatchtowerBot/1.0", no_sandbox: bool = False, watch_selectors: list[str] | None = None, ignore_selectors: list[str] | None = None, min_domain_interval_s: float = 1.0, cache_seconds: float = 3.0) -> PageSnapshot:
    from playwright.sync_api import Error as PlaywrightError
    from playwright.sync_api import TimeoutError as PlaywrightTimeout
    from playwright.sync_api import sync_playwright

    validate_public_url(url)  # re-validate at fetch time (DNS may have changed since the monitor was saved)
    cache_key = hashlib.sha256((url + "|" + repr(watch_selectors or []) + "|" + repr(ignore_selectors or [])).encode()).hexdigest()
    with _FETCH_LOCK:
        cached = _FETCH_CACHE.get(cache_key)
        if cached and time.monotonic() - cached[0] <= max(0, cache_seconds):
            return cached[1]
    _throttle_domain(url, min_domain_interval_s)

    state: dict = {"blocked_main": None}
    cache: dict[str, bool] = {}

    def handler(route):
        request = route.request
        if _request_allowed(request.url, cache):
            route.continue_()
            return
        try:
            is_main = request.is_navigation_request() and request.frame.parent_frame is None
        except Exception:
            is_main = False
        if is_main:
            state["blocked_main"] = request.url
        route.abort("blockedbyclient")

    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(headless=True, args=["--no-sandbox"] if no_sandbox else [])
        except PlaywrightError as exc:
            raise FetchError("The browser could not start. Run `python -m playwright install chromium`.") from exc

        try:
            context = browser.new_context(
                viewport={"width": 1280, "height": 800},
                user_agent=user_agent,
                service_workers="block",
                accept_downloads=False,
            )
            context.set_default_timeout(timeout_s * 1000)
            context.route("**/*", handler)
            page = context.new_page()

            try:
                response = page.goto(url, wait_until="domcontentloaded", timeout=timeout_s * 1000)
            except PlaywrightTimeout:
                raise FetchError(f"The page didn't load within {timeout_s} seconds.") from None
            except PlaywrightError as exc:
                if state["blocked_main"]:
                    raise FetchError("The page redirected to a private or blocked address.") from None
                raise FetchError(_friendly_error(exc)) from None

            if state["blocked_main"]:
                raise FetchError("The page redirected to a private or blocked address.")
            if response is None:
                raise FetchError("The site returned no response.")
            if response.status in (403, 429, 503):
                # These statuses are common for anti-bot challenges; inspect visible challenge text below too.
                status_warning = response.status
            else:
                status_warning = None
            if response.status >= 400 and status_warning is None:
                raise FetchError(f"The site responded with HTTP {response.status}.")

            ctype = (response.headers.get("content-type") or "").lower()
            if ctype and not any(t in ctype for t in ("html", "text/plain", "xml")):
                raise FetchError(f"Unsupported content type: {ctype.split(';')[0]}.")

            # Let client-rendered content settle. Busy pages never go idle, so a timeout here is fine.
            try:
                page.wait_for_load_state("networkidle", timeout=min(10_000, timeout_s * 1000))
            except PlaywrightTimeout:
                pass
            page.wait_for_timeout(500)

            screenshot = None
            try:
                screenshot = page.screenshot(type="jpeg", quality=70, full_page=False)
            except PlaywrightError:
                logger.info("Screenshot failed for %s", url)

            data = page.evaluate(EXTRACT_JS, {"watch": watch_selectors or [], "ignore": ignore_selectors or []})
            text = (data.get("text") or "")[:MAX_TEXT_CHARS]
            challenge_text = (data.get("title", "") + " " + text[:12000]).lower()
            challenge_markers = ("captcha", "verify you are human", "checking your browser",
                                 "security check", "challenge-platform", "cf-chl-", "unusual traffic")
            if status_warning or any(marker in challenge_text for marker in challenge_markers):
                raise FetchError("A CAPTCHA or anti-bot challenge was detected. Watchtower will retry later; it does not attempt to bypass challenges.")
            if not text.strip():
                raise FetchError("The page had no readable text. It may need a login or block automated browsers.")

            result = PageSnapshot(
                final_url=page.url,
                title=data.get("title") or "",
                text=text,
                screenshot=screenshot,
                http_status=response.status,
                preview_html=(data.get("html") or "")[:1_000_000],
                preview_styles=(data.get("styles") or "")[:200_000],
            )
            with _FETCH_LOCK:
                _FETCH_CACHE[cache_key] = (time.monotonic(), result)
                if len(_FETCH_CACHE) > 256:
                    for old_key, _ in sorted(_FETCH_CACHE.items(), key=lambda item: item[1][0])[:64]:
                        _FETCH_CACHE.pop(old_key, None)
            return result
        finally:
            browser.close()

def fetch_preview_html(url: str, *, timeout_s: int = 30, user_agent: str = "WatchtowerBot/1.0", no_sandbox: bool = False) -> dict:
    """Fetch a safe, script-free DOM snapshot for the visual selector picker."""
    snap = fetch_page(url, timeout_s=timeout_s, user_agent=user_agent, no_sandbox=no_sandbox)
    return {"title": snap.title, "url": snap.final_url, "html": snap.preview_html, "styles": snap.preview_styles}
