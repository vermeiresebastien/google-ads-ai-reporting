from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

from gads.models import PlatformConnection


@dataclass(frozen=True)
class Platform:
    id: str
    label: str
    search_terms: bool
    changes: bool
    credential_env: tuple[str, ...]
    sync_ready: bool = False


PLATFORMS: dict[str, Platform] = {
    "google": Platform(
        "google",
        "Google Ads",
        True,
        True,
        ("GOOGLE_ADS_CLIENT_ID", "GOOGLE_ADS_CLIENT_SECRET", "GOOGLE_ADS_DEVELOPER_TOKEN"),
        sync_ready=True,
    ),
    "microsoft": Platform(
        "microsoft",
        "Microsoft Advertising",
        True,
        False,
        ("MICROSOFT_ADS_CLIENT_ID", "MICROSOFT_ADS_CLIENT_SECRET", "MICROSOFT_ADS_DEVELOPER_TOKEN"),
    ),
    "meta": Platform("meta", "Meta", False, False, ("META_APP_ID", "META_APP_SECRET")),
    "linkedin": Platform("linkedin", "LinkedIn", False, False, ("LINKEDIN_CLIENT_ID", "LINKEDIN_CLIENT_SECRET")),
    "x": Platform("x", "X", False, False, ("X_CLIENT_ID", "X_CLIENT_SECRET")),
    "reddit": Platform("reddit", "Reddit", False, False, ("REDDIT_CLIENT_ID", "REDDIT_CLIENT_SECRET")),
}


def platform_spec(platform_id: str | None) -> Platform:
    if platform_id in PLATFORMS:
        return PLATFORMS[platform_id]
    return Platform(platform_id or "google", platform_id or "Google Ads", False, False, ())


def account_public(account) -> dict:
    spec = platform_spec(getattr(account, "platform", None) or "google")
    synced = account.last_successful_sync_at
    return {
        "id": account.id,
        "workspace_id": account.workspace_id,
        "platform": spec.id,
        "platform_label": spec.label,
        "search_terms": spec.search_terms,
        "changes": spec.changes,
        "sync_ready": spec.sync_ready,
        "customer_id": account.customer_id,
        "manager_customer_id": account.manager_customer_id,
        "account_name": account.account_name,
        "currency_code": account.currency_code,
        "timezone": account.timezone,
        "status": account.status,
        "last_successful_sync_at": synced.isoformat() if synced else None,
    }


def ensure_account_platform(engine: Engine) -> None:
    ensure_multi_platform_schema(engine)


def ensure_multi_platform_schema(engine: Engine) -> None:
    inspector = inspect(engine)
    PlatformConnection.__table__.create(bind=engine, checkfirst=True)
    if not inspector.has_table("ad_accounts"):
        return
    names = {column["name"] for column in inspector.get_columns("ad_accounts")}
    with engine.begin() as connection:
        if "platform" not in names:
            connection.execute(text("ALTER TABLE ad_accounts ADD COLUMN platform VARCHAR(32) DEFAULT 'google' NOT NULL"))
        if "platform_connection_id" not in names:
            connection.execute(text("ALTER TABLE ad_accounts ADD COLUMN platform_connection_id VARCHAR(36)"))
    _ensure_nullable_google_connection(engine)


def _ensure_nullable_google_connection(engine: Engine) -> None:
    url = str(engine.url)
    if url.startswith("sqlite"):
        with engine.begin() as connection:
            rows = connection.execute(text("PRAGMA table_info(ad_accounts)")).mappings().all()
            connection_col = next((row for row in rows if row["name"] == "connection_id"), None)
            if connection_col is None or connection_col["notnull"] == 0:
                return
            connection.execute(text("PRAGMA foreign_keys=OFF"))
            connection.execute(text("ALTER TABLE ad_accounts RENAME TO ad_accounts_old"))
            connection.execute(
                text(
                    """
                    CREATE TABLE ad_accounts (
                        id VARCHAR(36) NOT NULL PRIMARY KEY,
                        workspace_id VARCHAR(36) NOT NULL,
                        connection_id VARCHAR(36),
                        platform_connection_id VARCHAR(36),
                        platform VARCHAR(32) DEFAULT 'google' NOT NULL,
                        customer_id VARCHAR(64) NOT NULL,
                        manager_customer_id VARCHAR(64),
                        account_name VARCHAR(255) DEFAULT '' NOT NULL,
                        currency_code VARCHAR(8) DEFAULT '' NOT NULL,
                        timezone VARCHAR(64) DEFAULT '' NOT NULL,
                        status VARCHAR(32) DEFAULT 'ENABLED' NOT NULL,
                        last_successful_sync_at DATETIME,
                        created_at DATETIME NOT NULL,
                        updated_at DATETIME NOT NULL,
                        FOREIGN KEY(workspace_id) REFERENCES workspaces (id) ON DELETE CASCADE,
                        FOREIGN KEY(connection_id) REFERENCES google_connections (id) ON DELETE CASCADE,
                        FOREIGN KEY(platform_connection_id) REFERENCES platform_connections (id) ON DELETE CASCADE,
                        UNIQUE (workspace_id, platform, customer_id)
                    )
                    """
                )
            )
            old_names = {row["name"] for row in rows}
            has_platform = "platform" in old_names
            has_platform_connection = "platform_connection_id" in old_names
            connection.execute(
                text(
                    f"""
                    INSERT INTO ad_accounts (
                        id, workspace_id, connection_id, platform_connection_id, platform, customer_id,
                        manager_customer_id, account_name, currency_code, timezone, status,
                        last_successful_sync_at, created_at, updated_at
                    )
                    SELECT
                        id, workspace_id, connection_id,
                        {"platform_connection_id" if has_platform_connection else "NULL"},
                        {"platform" if has_platform else "'google'"},
                        customer_id, manager_customer_id, account_name, currency_code, timezone, status,
                        last_successful_sync_at, created_at, updated_at
                    FROM ad_accounts_old
                    """
                )
            )
            connection.execute(text("DROP TABLE ad_accounts_old"))
            connection.execute(text("PRAGMA foreign_keys=ON"))
        return
    try:
        with engine.begin() as connection:
            connection.execute(text("ALTER TABLE ad_accounts ALTER COLUMN connection_id DROP NOT NULL"))
    except Exception:
        return
