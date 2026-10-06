from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Resolve .env from the repo root regardless of uvicorn cwd.
_REPO_ROOT = Path(__file__).resolve().parents[2]
_ENV_FILE = _REPO_ROOT / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=str(_ENV_FILE), env_file_encoding="utf-8", extra="ignore")

    database_url: str = "postgresql+psycopg://gads:gads@localhost:5432/gads"
    redis_url: str = "redis://localhost:6379/0"
    jwt_secret: str = "dev-only-change-me"
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 60 * 24 * 7
    token_encryption_key: str = ""

    google_ads_developer_token: str = ""
    google_ads_client_id: str = ""
    google_ads_client_secret: str = ""
    google_ads_login_customer_id: str = ""
    google_oauth_redirect_uri: str = "http://localhost:8000/api/google/oauth/callback"
    google_ads_api_version: str = "v25"

    microsoft_ads_client_id: str = ""
    microsoft_ads_client_secret: str = ""
    microsoft_ads_developer_token: str = ""
    meta_app_id: str = ""
    meta_app_secret: str = ""
    linkedin_client_id: str = ""
    linkedin_client_secret: str = ""
    x_client_id: str = ""
    x_client_secret: str = ""
    reddit_client_id: str = ""
    reddit_client_secret: str = ""
    # OAuth callbacks use {GADS_API_BASE_URL}/api/platforms/{platform}/oauth/callback

    sync_initial_lookback_days: int = 90
    sync_history_lookback_days: int = 395
    ingest_max_days: int = 400
    tool_max_days: int = 400
    tool_max_rows: int = 100

    frontend_url: str = "http://localhost:3000"
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"

    openai_api_key: str = ""
    openai_model: str = "gpt-4.1-mini"
    openrouter_api_key: str = ""
    openrouter_backup_api_key: str = ""
    council_models: str = "openai/gpt-5.1,google/gemini-3-pro-preview,anthropic/claude-sonnet-4.5,x-ai/grok-4"
    chairman_model: str = "google/gemini-3-pro-preview"
    sentry_dsn: str = ""

    gads_api_base_url: str = "http://localhost:8000"
    gads_api_token: str = ""
    # Live Google Ads writes require explicit opt-in plus per-action confirm=true.
    allow_google_mutations: bool = False
    budget_increase_pct: float = 0.20

    def cors_origin_list(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
