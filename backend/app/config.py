from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BASE_DIR / ".env", env_file_encoding="utf-8", extra="ignore")

    data_dir: Path = BASE_DIR / "data"
    database_url: str = f"sqlite:///{BASE_DIR / 'data' / 'watchtower.db'}"
    screenshots_dir: Path = BASE_DIR / "data" / "screenshots"

    discord_webhook_url: str = ""
    email_enabled: bool = False
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from: str = ""
    smtp_to: str = ""
    smtp_starttls: bool = True
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    daily_digest_enabled: bool = False
    daily_digest_hour: int = 9
    domain_min_interval_seconds: float = 1.0
    fetch_cache_seconds: float = 3.0
    fetch_retry_attempts: int = 3
    public_dashboard_url: str = "http://localhost:5173"
    cors_origins: str = "http://localhost:5173"

    demo_mode: bool = False
    scheduler_enabled: bool = True
    scheduler_tick_seconds: int = 30
    max_concurrent_checks: int = 2
    page_timeout_seconds: int = 30
    notify_dedup_hours: int = 24
    max_history_per_monitor: int = 100
    playwright_no_sandbox: bool = False
    user_agent: str = "WatchtowerBot/1.0 (website change monitor)"


@lru_cache
def get_settings() -> Settings:
    return Settings()