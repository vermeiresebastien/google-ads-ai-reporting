from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def new_id() -> str:
    return str(uuid.uuid4())


def utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


def _non_negative(prefix: str):
    columns = (
        "impressions",
        "clicks",
        "cost",
        "cost_micros",
        "conversions",
        "conversion_value",
    )
    return tuple(CheckConstraint(f"{column} >= 0", name=f"ck_{prefix}_{column}") for column in columns)


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    memberships: Mapped[list[WorkspaceMember]] = relationship(back_populates="user")


class Workspace(Base):
    __tablename__ = "workspaces"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    members: Mapped[list[WorkspaceMember]] = relationship(back_populates="workspace")
    connections: Mapped[list[GoogleConnection]] = relationship(back_populates="workspace")
    platform_connections: Mapped[list[PlatformConnection]] = relationship(back_populates="workspace")
    accounts: Mapped[list[AdAccount]] = relationship(back_populates="workspace")


class WorkspaceMember(Base):
    __tablename__ = "workspace_members"

    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    role: Mapped[str] = mapped_column(String(32), default="member")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    workspace: Mapped[Workspace] = relationship(back_populates="members")
    user: Mapped[User] = relationship(back_populates="memberships")


class GoogleConnection(Base):
    __tablename__ = "google_connections"
    __table_args__ = (UniqueConstraint("workspace_id", "google_email", name="uq_connection_email"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), index=True)
    google_email: Mapped[str] = mapped_column(String(320), default="")
    refresh_token_encrypted: Mapped[str] = mapped_column(Text)
    access_token_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    access_token_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    workspace: Mapped[Workspace] = relationship(back_populates="connections")
    accounts: Mapped[list[AdAccount]] = relationship(back_populates="connection")


class PlatformConnection(Base):
    __tablename__ = "platform_connections"
    __table_args__ = (UniqueConstraint("workspace_id", "platform", "external_user_id", name="uq_platform_user"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), index=True)
    platform: Mapped[str] = mapped_column(String(32))
    external_user_id: Mapped[str] = mapped_column(String(255), default="")
    external_email: Mapped[str] = mapped_column(String(320), default="")
    refresh_token_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    access_token_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    access_token_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    workspace: Mapped[Workspace] = relationship(back_populates="platform_connections")
    accounts: Mapped[list[AdAccount]] = relationship(back_populates="platform_connection")


class AdAccount(Base):
    __tablename__ = "ad_accounts"
    __table_args__ = (UniqueConstraint("workspace_id", "platform", "customer_id", name="uq_account_platform_customer"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), index=True)
    connection_id: Mapped[str | None] = mapped_column(ForeignKey("google_connections.id", ondelete="CASCADE"), nullable=True, index=True)
    platform_connection_id: Mapped[str | None] = mapped_column(
        ForeignKey("platform_connections.id", ondelete="CASCADE"), nullable=True, index=True
    )
    platform: Mapped[str] = mapped_column(String(32), default="google")
    customer_id: Mapped[str] = mapped_column(String(64))
    manager_customer_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    account_name: Mapped[str] = mapped_column(String(255), default="")
    currency_code: Mapped[str] = mapped_column(String(8), default="")
    timezone: Mapped[str] = mapped_column(String(64), default="")
    status: Mapped[str] = mapped_column(String(32), default="ENABLED")
    last_successful_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    workspace: Mapped[Workspace] = relationship(back_populates="accounts")
    connection: Mapped[GoogleConnection | None] = relationship(back_populates="accounts")
    platform_connection: Mapped[PlatformConnection | None] = relationship(back_populates="accounts")
    campaigns: Mapped[list[Campaign]] = relationship(back_populates="account", cascade="all, delete-orphan")


class Campaign(Base):
    __tablename__ = "campaigns"
    __table_args__ = (UniqueConstraint("account_id", "google_campaign_id", name="uq_campaign_google"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    account_id: Mapped[str] = mapped_column(ForeignKey("ad_accounts.id", ondelete="CASCADE"), index=True)
    google_campaign_id: Mapped[str] = mapped_column(String(32))
    name: Mapped[str] = mapped_column(String(255), default="")
    campaign_type: Mapped[str] = mapped_column(String(64), default="")
    advertising_channel_type: Mapped[str] = mapped_column(String(64), default="")
    status: Mapped[str] = mapped_column(String(32), default="")
    daily_budget: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    account: Mapped[AdAccount] = relationship(back_populates="campaigns")


class AdGroup(Base):
    __tablename__ = "ad_groups"
    __table_args__ = (UniqueConstraint("account_id", "google_ad_group_id", name="uq_ad_group_google"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    account_id: Mapped[str] = mapped_column(ForeignKey("ad_accounts.id", ondelete="CASCADE"), index=True)
    google_ad_group_id: Mapped[str] = mapped_column(String(32))
    campaign_id: Mapped[str | None] = mapped_column(ForeignKey("campaigns.id", ondelete="SET NULL"), nullable=True)
    name: Mapped[str] = mapped_column(String(255), default="")
    status: Mapped[str] = mapped_column(String(32), default="")
    type: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class Keyword(Base):
    __tablename__ = "keywords"
    __table_args__ = (
        UniqueConstraint("account_id", "ad_group_id", "google_criterion_id", name="uq_keyword_google"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    account_id: Mapped[str] = mapped_column(ForeignKey("ad_accounts.id", ondelete="CASCADE"), index=True)
    google_criterion_id: Mapped[str] = mapped_column(String(32))
    campaign_id: Mapped[str | None] = mapped_column(ForeignKey("campaigns.id", ondelete="SET NULL"), nullable=True)
    ad_group_id: Mapped[str | None] = mapped_column(ForeignKey("ad_groups.id", ondelete="SET NULL"), nullable=True)
    keyword_text: Mapped[str] = mapped_column(String(500), default="")
    match_type: Mapped[str] = mapped_column(String(32), default="")
    status: Mapped[str] = mapped_column(String(32), default="")
    quality_score: Mapped[int | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class Ad(Base):
    __tablename__ = "ads"
    __table_args__ = (UniqueConstraint("account_id", "ad_group_id", "google_ad_id", name="uq_ad_google"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    account_id: Mapped[str] = mapped_column(ForeignKey("ad_accounts.id", ondelete="CASCADE"), index=True)
    google_ad_id: Mapped[str] = mapped_column(String(32))
    campaign_id: Mapped[str | None] = mapped_column(ForeignKey("campaigns.id", ondelete="SET NULL"), nullable=True)
    ad_group_id: Mapped[str | None] = mapped_column(ForeignKey("ad_groups.id", ondelete="SET NULL"), nullable=True)
    ad_type: Mapped[str] = mapped_column(String(64), default="")
    status: Mapped[str] = mapped_column(String(32), default="")
    final_url: Mapped[str] = mapped_column(Text, default="")
    headline_data: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)
    description_data: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class CampaignDaily(Base):
    __tablename__ = "campaign_daily"
    __table_args__ = _non_negative("campaign_daily")

    account_id: Mapped[str] = mapped_column(ForeignKey("ad_accounts.id", ondelete="CASCADE"), primary_key=True)
    date: Mapped[date] = mapped_column(Date, primary_key=True)
    campaign_id: Mapped[str] = mapped_column(ForeignKey("campaigns.id", ondelete="CASCADE"), primary_key=True)
    impressions: Mapped[int] = mapped_column(default=0)
    clicks: Mapped[int] = mapped_column(default=0)
    cost_micros: Mapped[int] = mapped_column(default=0)
    cost: Mapped[Decimal] = mapped_column(Numeric(18, 6), default=0)
    conversions: Mapped[Decimal] = mapped_column(Numeric(18, 6), default=0)
    conversion_value: Mapped[Decimal] = mapped_column(Numeric(18, 6), default=0)
    ctr: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    average_cpc: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    average_cpm: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    conversion_rate: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    cost_per_conversion: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    roas: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    search_impression_share: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    search_budget_lost_impression_share: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    search_rank_lost_impression_share: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)


class AdGroupDaily(Base):
    __tablename__ = "ad_group_daily"
    __table_args__ = _non_negative("ad_group_daily")

    account_id: Mapped[str] = mapped_column(ForeignKey("ad_accounts.id", ondelete="CASCADE"), primary_key=True)
    date: Mapped[date] = mapped_column(Date, primary_key=True)
    ad_group_id: Mapped[str] = mapped_column(ForeignKey("ad_groups.id", ondelete="CASCADE"), primary_key=True)
    campaign_id: Mapped[str | None] = mapped_column(ForeignKey("campaigns.id", ondelete="SET NULL"), nullable=True)
    impressions: Mapped[int] = mapped_column(default=0)
    clicks: Mapped[int] = mapped_column(default=0)
    cost_micros: Mapped[int] = mapped_column(default=0)
    cost: Mapped[Decimal] = mapped_column(Numeric(18, 6), default=0)
    conversions: Mapped[Decimal] = mapped_column(Numeric(18, 6), default=0)
    conversion_value: Mapped[Decimal] = mapped_column(Numeric(18, 6), default=0)
    ctr: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    average_cpc: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    conversion_rate: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    cost_per_conversion: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    roas: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)


class KeywordDaily(Base):
    __tablename__ = "keyword_daily"
    __table_args__ = _non_negative("keyword_daily")

    account_id: Mapped[str] = mapped_column(ForeignKey("ad_accounts.id", ondelete="CASCADE"), primary_key=True)
    date: Mapped[date] = mapped_column(Date, primary_key=True)
    keyword_id: Mapped[str] = mapped_column(ForeignKey("keywords.id", ondelete="CASCADE"), primary_key=True)
    campaign_id: Mapped[str | None] = mapped_column(ForeignKey("campaigns.id", ondelete="SET NULL"), nullable=True)
    ad_group_id: Mapped[str | None] = mapped_column(ForeignKey("ad_groups.id", ondelete="SET NULL"), nullable=True)
    impressions: Mapped[int] = mapped_column(default=0)
    clicks: Mapped[int] = mapped_column(default=0)
    cost_micros: Mapped[int] = mapped_column(default=0)
    cost: Mapped[Decimal] = mapped_column(Numeric(18, 6), default=0)
    conversions: Mapped[Decimal] = mapped_column(Numeric(18, 6), default=0)
    conversion_value: Mapped[Decimal] = mapped_column(Numeric(18, 6), default=0)
    ctr: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    average_cpc: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    conversion_rate: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    cost_per_conversion: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    roas: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    quality_score: Mapped[int | None] = mapped_column(nullable=True)


class SearchTermDaily(Base):
    __tablename__ = "search_terms_daily"
    __table_args__ = (
        UniqueConstraint(
            "account_id",
            "date",
            "source",
            "campaign_id",
            "ad_group_id",
            "search_term",
            "keyword_resource",
            "match_type",
            name="uq_search_term_daily",
        ),
        *_non_negative("search_terms_daily"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    account_id: Mapped[str] = mapped_column(ForeignKey("ad_accounts.id", ondelete="CASCADE"), index=True)
    date: Mapped[date] = mapped_column(Date, index=True)
    source: Mapped[str] = mapped_column(String(32))
    campaign_id: Mapped[str] = mapped_column(String(36), default="")
    ad_group_id: Mapped[str] = mapped_column(String(36), default="")
    search_term: Mapped[str] = mapped_column(String(2048))
    keyword_id: Mapped[str | None] = mapped_column(ForeignKey("keywords.id", ondelete="SET NULL"), nullable=True)
    keyword_resource: Mapped[str] = mapped_column(String(512), default="")
    match_type: Mapped[str] = mapped_column(String(64), default="")
    impressions: Mapped[int] = mapped_column(default=0)
    clicks: Mapped[int] = mapped_column(default=0)
    cost_micros: Mapped[int] = mapped_column(default=0)
    cost: Mapped[Decimal] = mapped_column(Numeric(18, 6), default=0)
    conversions: Mapped[Decimal] = mapped_column(Numeric(18, 6), default=0)
    conversion_value: Mapped[Decimal] = mapped_column(Numeric(18, 6), default=0)
    ctr: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    average_cpc: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    conversion_rate: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    cost_per_conversion: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    roas: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)


class CampaignBudgetDaily(Base):
    __tablename__ = "campaign_budget_daily"
    __table_args__ = (
        CheckConstraint("budget >= 0", name="ck_budget_daily_budget"),
        CheckConstraint("spend >= 0", name="ck_budget_daily_spend"),
        CheckConstraint("impressions >= 0", name="ck_budget_daily_impressions"),
    )

    account_id: Mapped[str] = mapped_column(ForeignKey("ad_accounts.id", ondelete="CASCADE"), primary_key=True)
    date: Mapped[date] = mapped_column(Date, primary_key=True)
    campaign_id: Mapped[str] = mapped_column(ForeignKey("campaigns.id", ondelete="CASCADE"), primary_key=True)
    budget: Mapped[Decimal] = mapped_column(Numeric(18, 6), default=0)
    spend: Mapped[Decimal] = mapped_column(Numeric(18, 6), default=0)
    budget_utilization: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    impressions: Mapped[int] = mapped_column(default=0)
    lost_impression_share_budget: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)


class ChangeEvent(Base):
    __tablename__ = "change_events"
    __table_args__ = (UniqueConstraint("account_id", "resource_name", name="uq_change_event"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    account_id: Mapped[str] = mapped_column(ForeignKey("ad_accounts.id", ondelete="CASCADE"), index=True)
    resource_name: Mapped[str] = mapped_column(String(512))
    event_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    resource_type: Mapped[str] = mapped_column(String(64), default="")
    resource_changed_name: Mapped[str] = mapped_column(String(512), default="")
    change_type: Mapped[str] = mapped_column(String(64), default="")
    field_changed: Mapped[str] = mapped_column(Text, default="")
    old_value: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    new_value: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    client_type: Mapped[str] = mapped_column(String(64), default="")
    user_email: Mapped[str] = mapped_column(String(320), default="")
    raw_payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class RawGoogleAdsRow(Base):
    __tablename__ = "raw_google_ads_rows"
    __table_args__ = (
        UniqueConstraint(
            "account_id",
            "dataset",
            "google_resource_name",
            "report_date",
            name="uq_raw_row",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    account_id: Mapped[str] = mapped_column(ForeignKey("ad_accounts.id", ondelete="CASCADE"), index=True)
    dataset: Mapped[str] = mapped_column(String(64))
    google_resource_name: Mapped[str] = mapped_column(String(512))
    report_date: Mapped[date] = mapped_column(Date)
    payload_json: Mapped[dict] = mapped_column(JSON)
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class SyncRun(Base):
    __tablename__ = "sync_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    account_id: Mapped[str] = mapped_column(ForeignKey("ad_accounts.id", ondelete="CASCADE"), index=True)
    dataset: Mapped[str] = mapped_column(String(64), index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    rows_fetched: Mapped[int] = mapped_column(default=0)
    rows_inserted: Mapped[int] = mapped_column(default=0)
    rows_updated: Mapped[int] = mapped_column(default=0)
    api_request_count: Mapped[int] = mapped_column(default=0)
    status: Mapped[str] = mapped_column(String(32), default="running")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)


class SavedReport(Base):
    __tablename__ = "saved_reports"
    __table_args__ = (UniqueConstraint("account_id", "report_date", "kind", name="uq_saved_report"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    account_id: Mapped[str] = mapped_column(ForeignKey("ad_accounts.id", ondelete="CASCADE"), index=True)
    report_date: Mapped[date] = mapped_column(Date, index=True)
    kind: Mapped[str] = mapped_column(String(64))
    period_start: Mapped[date | None] = mapped_column(Date, nullable=True)
    period_end: Mapped[date | None] = mapped_column(Date, nullable=True)
    question: Mapped[str] = mapped_column(Text, default="")
    title: Mapped[str] = mapped_column(String(200), default="")
    body: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    highlights: Mapped[list["SavedReportHighlight"]] = relationship(
        back_populates="report", cascade="all, delete-orphan"
    )


class SavedReportHighlight(Base):
    __tablename__ = "saved_report_highlights"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    saved_report_id: Mapped[str] = mapped_column(ForeignKey("saved_reports.id", ondelete="CASCADE"), index=True)
    quote: Mapped[str] = mapped_column(Text)
    color: Mapped[str] = mapped_column(String(16))
    note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    report: Mapped[SavedReport] = relationship(back_populates="highlights")


class AccountAnalyticsSettings(Base):
    __tablename__ = "account_analytics_settings"

    account_id: Mapped[str] = mapped_column(ForeignKey("ad_accounts.id", ondelete="CASCADE"), primary_key=True)
    min_spend_for_waste: Mapped[Decimal] = mapped_column(Numeric(18, 6), default=50)
    spend_anomaly_pct: Mapped[Decimal] = mapped_column(Numeric(18, 6), default=Decimal("0.30"))
    cpa_anomaly_pct: Mapped[Decimal] = mapped_column(Numeric(18, 6), default=Decimal("0.25"))
    roas_anomaly_pct: Mapped[Decimal] = mapped_column(Numeric(18, 6), default=Decimal("0.20"))
    conversion_anomaly_pct: Mapped[Decimal] = mapped_column(Numeric(18, 6), default=Decimal("0.25"))
    cpc_anomaly_pct: Mapped[Decimal] = mapped_column(Numeric(18, 6), default=Decimal("0.25"))
    cvr_anomaly_pct: Mapped[Decimal] = mapped_column(Numeric(18, 6), default=Decimal("0.20"))
    zero_conversion_min_spend: Mapped[Decimal] = mapped_column(Numeric(18, 6), default=25)
    budget_lost_is_min: Mapped[Decimal] = mapped_column(Numeric(18, 6), default=Decimal("0.15"))
    min_clicks: Mapped[int] = mapped_column(default=10)
    min_spend_for_anomaly: Mapped[Decimal] = mapped_column(Numeric(18, 6), default=20)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class SettingsPreset(Base):
    __tablename__ = "settings_presets"
    __table_args__ = (UniqueConstraint("account_id", "name"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    account_id: Mapped[str] = mapped_column(ForeignKey("ad_accounts.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(80))
    values: Mapped[dict] = mapped_column(JSON)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
