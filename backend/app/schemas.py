from typing import Annotated, Literal
import json

from pydantic import BaseModel, Field, StringConstraints, field_validator

from .notifications.discord import is_valid_webhook_url

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]
IntervalMinutes = Literal[15, 60, 360, 1440]
INTERVALS = (15, 60, 360, 1440)


def _clean_focus(v: str | None) -> str | None:
    if v is None:
        return None
    v = v.strip()
    return v or None


def _check_webhook(v: str | None) -> str | None:
    if v is None:
        return None
    v = v.strip()
    if v and not is_valid_webhook_url(v):
        raise ValueError("That doesn't look like a Discord webhook URL (https://discord.com/api/webhooks/...).")
    return v


class MonitorCreate(BaseModel):
    name: Name
    url: str = Field(min_length=1, max_length=2048)
    interval_minutes: IntervalMinutes = 60
    focus: str | None = Field(default=None, max_length=200)
    sensitivity: int = Field(default=2, ge=1, le=3)
    notify_discord: bool = True
    notify_email: bool = False
    notify_telegram: bool = False
    notify_on_error: bool = False
    discord_webhook_url: str | None = Field(default=None, max_length=300)
    watch_selectors: list[str] = Field(default_factory=list, max_length=30)
    ignore_selectors: list[str] = Field(default_factory=list, max_length=30)

    @field_validator("focus")
    @classmethod
    def clean_focus(cls, v):
        return _clean_focus(v)

    @field_validator("discord_webhook_url")
    @classmethod
    def check_webhook(cls, v):
        return _check_webhook(v)


class MonitorUpdate(BaseModel):
    name: Name | None = None
    url: str | None = Field(default=None, min_length=1, max_length=2048)
    interval_minutes: IntervalMinutes | None = None
    focus: str | None = Field(default=None, max_length=200)
    sensitivity: int | None = Field(default=None, ge=1, le=3)
    notify_discord: bool | None = None
    notify_email: bool | None = None
    notify_telegram: bool | None = None
    notify_on_error: bool | None = None
    # "" clears the stored webhook, omitted leaves it unchanged
    discord_webhook_url: str | None = Field(default=None, max_length=300)
    watch_selectors: list[str] | None = Field(default=None, max_length=30)
    ignore_selectors: list[str] | None = Field(default=None, max_length=30)

    @field_validator("focus")
    @classmethod
    def clean_focus(cls, v):
        return _clean_focus(v)

    @field_validator("discord_webhook_url")
    @classmethod
    def check_webhook(cls, v):
        return _check_webhook(v)