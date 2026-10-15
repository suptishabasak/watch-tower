from .base import ChangeEvent, Notifier, dispatch
from .discord import DiscordNotifier, build_notifiers as build_discord_notifiers
from .email import EmailNotifier
from .telegram import TelegramNotifier

def build_notifiers(monitor, settings, force: bool = False):
    result = []
    if force or getattr(monitor, "notify_discord", False):
        url = getattr(monitor, "discord_webhook_url", None) or getattr(settings, "discord_webhook_url", "")
        if url:
            result.extend(build_discord_notifiers(monitor, settings, force=force))
    if getattr(monitor, "notify_email", False) or (force and getattr(settings, "email_enabled", False)):
        if getattr(settings, "email_enabled", False):
            result.append(EmailNotifier(getattr(settings, "smtp_host", ""), getattr(settings, "smtp_port", 587), getattr(settings, "smtp_username", ""),
                                        getattr(settings, "smtp_password", ""), getattr(settings, "smtp_from", ""), getattr(settings, "smtp_to", ""),
                                        getattr(settings, "smtp_starttls", True)))
    if getattr(monitor, "notify_telegram", False) or (force and getattr(settings, "telegram_bot_token", "") and getattr(settings, "telegram_chat_id", "")):
        if getattr(settings, "telegram_bot_token", "") and getattr(settings, "telegram_chat_id", ""):
            result.append(TelegramNotifier(getattr(settings, "telegram_bot_token", ""), getattr(settings, "telegram_chat_id", "")))
    return result

__all__ = ["ChangeEvent", "Notifier", "DiscordNotifier", "EmailNotifier", "TelegramNotifier", "build_notifiers", "dispatch"]
