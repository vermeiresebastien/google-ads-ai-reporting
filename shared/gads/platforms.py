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
    if str(engine.url).startswith("sqlite"):
        repair_sqlite_ad_account_foreign_keys(engine)
        return
    try:
        with engine.begin() as connection:
            connection.execute(text("ALTER TABLE ad_accounts ALTER COLUMN connection_id DROP NOT NULL"))
    except Exception:
        return


def repair_sqlite_ad_account_foreign_keys(engine: Engine) -> None:
    """SQLite renames update FK targets, so a rebuild of ad_accounts can leave dependents on ad_accounts_old."""
    import re

    with engine.begin() as connection:
        connection.execute(text("PRAGMA foreign_keys=OFF"))
        tables = [
            row[0]
            for row in connection.execute(text("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"))
        ]
        damaged = []
        for name in tables:
            if name.startswith("sqlite_") or name.endswith("__fkfix"):
                continue
            fks = list(connection.execute(text(f'PRAGMA foreign_key_list("{name}")')))
            if any(fk[2] == "ad_accounts_old" for fk in fks):
                damaged.append(name)
        for name in damaged:
            row = connection.execute(
                text("SELECT sql FROM sqlite_master WHERE type='table' AND name=:name"),
                {"name": name},
            ).fetchone()
            if row is None or not row[0]:
                continue
            create_sql = row[0].replace('"ad_accounts_old"', "ad_accounts").replace("ad_accounts_old", "ad_accounts")
            temp = f"{name}__fkfix"
            create_sql = re.sub(
                rf'CREATE TABLE\s+["\']?{re.escape(name)}["\']?',
                f'CREATE TABLE "{temp}"',
                create_sql,
                count=1,
                flags=re.IGNORECASE,
            )
            connection.execute(text(create_sql))
            columns = [
                column["name"]
                for column in connection.execute(text(f'PRAGMA table_info("{name}")')).mappings()
            ]
            quoted = ", ".join(f'"{column}"' for column in columns)
            connection.execute(text(f'INSERT INTO "{temp}" ({quoted}) SELECT {quoted} FROM "{name}"'))
            connection.execute(text(f'DROP TABLE "{name}"'))
            connection.execute(text(f'ALTER TABLE "{temp}" RENAME TO "{name}"'))
        connection.execute(text("PRAGMA foreign_keys=ON"))


def ensure_proposed_actions_table(engine: Engine) -> None:
    from gads.models import ProposedAction

    ProposedAction.__table__.create(bind=engine, checkfirst=True)
