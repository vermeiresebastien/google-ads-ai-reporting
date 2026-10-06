from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from gads.models import (
    AccountAnalyticsSettings,
    AdAccount,
    Campaign,
    CampaignBudgetDaily,
    CampaignDaily,
    ChangeEvent,
    GoogleConnection,
    SearchTermDaily,
    User,
    Workspace,
    WorkspaceMember,
)
from gads.security import encrypt_secret, hash_password
from gads_analytics.metrics import Totals
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

FIXTURE_EMAIL = "analyst@example.com"
FIXTURE_PASSWORD = "password123"


def _daily(cost: float, clicks: int, impressions: int, conversions: float, value: float) -> Totals:
    return Totals(impressions=impressions, clicks=clicks, cost=cost, conversions=conversions, conversion_value=value)


def seed_report_account(session: Session, as_of: date | None = None) -> dict:
    as_of = as_of or (datetime.now(UTC).date() - timedelta(days=1))
    user = session.scalar(select(User).where(User.email == FIXTURE_EMAIL))
    if user is None:
        user = User(email=FIXTURE_EMAIL, password_hash=hash_password(FIXTURE_PASSWORD))
        session.add(user)
        session.flush()
        workspace = Workspace(name="Workspace")
        session.add(workspace)
        session.flush()
        session.add(WorkspaceMember(workspace_id=workspace.id, user_id=user.id, role="owner"))
        connection = GoogleConnection(
            workspace_id=workspace.id,
            google_email=FIXTURE_EMAIL,
            refresh_token_encrypted=encrypt_secret("refresh-token"),
            status="active",
        )
        session.add(connection)
        session.flush()
        account = AdAccount(
            workspace_id=workspace.id,
            connection_id=connection.id,
            customer_id="1234567890",
            account_name="Account",
            currency_code="EUR",
            timezone="Europe/Brussels",
            status="ENABLED",
            last_successful_sync_at=datetime.now(UTC),
        )
        session.add(account)
        session.flush()
        session.add(AccountAnalyticsSettings(account_id=account.id))
    else:
        membership = session.scalar(select(WorkspaceMember).where(WorkspaceMember.user_id == user.id))
        workspace = session.get(Workspace, membership.workspace_id)
        account = session.scalar(select(AdAccount).where(AdAccount.workspace_id == workspace.id))

    for model in (CampaignDaily, CampaignBudgetDaily, SearchTermDaily, ChangeEvent, Campaign):
        session.execute(delete(model).where(model.account_id == account.id))
    session.flush()

    specs = {
        "Brand Search": {"channel": "SEARCH"},
        "Non-brand Search": {"channel": "SEARCH"},
        "Competitor Terms": {"channel": "SEARCH"},
        "Prospecting Exact": {"channel": "SEARCH"},
    }
    campaigns = {}
    for name, spec in specs.items():
        row = Campaign(
            account_id=account.id,
            google_campaign_id=str(1000 + len(campaigns)),
            name=name,
            advertising_channel_type=spec["channel"],
            status="ENABLED",
            daily_budget=Decimal("200"),
        )
        session.add(row)
        session.flush()
        campaigns[name] = row

    def pattern(day_offset: int) -> dict[str, Totals]:
        nonbrand = _daily(230, 70, 3800, 6, 240) if day_offset == 1 else _daily(200, 80, 4000, 8, 320)
        return {
            "Brand Search": _daily(100, 50, 1000, 10, 400),
            "Non-brand Search": nonbrand,
            "Competitor Terms": _daily(40, 30, 2000, 0, 0),
            "Prospecting Exact": _daily(80, 40, 1500, 8, 480),
        }

    for offset in range(1, 15):
        day = as_of - timedelta(days=offset - 1)
        for name, totals in pattern(offset).items():
            derived = totals.derived()
            campaign = campaigns[name]
            session.add(
                CampaignDaily(
                    account_id=account.id,
                    date=day,
                    campaign_id=campaign.id,
                    impressions=int(totals.impressions),
                    clicks=int(totals.clicks),
                    cost_micros=int(totals.cost * 1_000_000),
                    cost=totals.cost,
                    conversions=totals.conversions,
                    conversion_value=totals.conversion_value,
                    ctr=derived["ctr"],
                    average_cpc=derived["average_cpc"],
                    average_cpm=derived["average_cpm"],
                    conversion_rate=derived["conversion_rate"],
                    cost_per_conversion=derived["cost_per_conversion"],
                    roas=derived["roas"],
                    search_impression_share=0.7,
                    search_budget_lost_impression_share=0.35 if name == "Prospecting Exact" else 0.02,
                    search_rank_lost_impression_share=0.05,
                )
            )
            budget = 90 if name == "Prospecting Exact" else 250
            session.add(
                CampaignBudgetDaily(
                    account_id=account.id,
                    date=day,
                    campaign_id=campaign.id,
                    budget=budget,
                    spend=totals.cost,
                    budget_utilization=None if budget == 0 else totals.cost / budget,
                    impressions=int(totals.impressions),
                    lost_impression_share_budget=0.35 if name == "Prospecting Exact" else 0.02,
                )
            )

    session.add(
        SearchTermDaily(
            account_id=account.id,
            date=as_of,
            source="ad_group",
            campaign_id=campaigns["Competitor Terms"].id,
            ad_group_id="",
            search_term="free competitor alternative",
            keyword_resource="",
            match_type="BROAD",
            impressions=400,
            clicks=40,
            cost_micros=80_000_000,
            cost=80,
            conversions=0,
            conversion_value=0,
            ctr=0.1,
            average_cpc=2,
            conversion_rate=None,
            cost_per_conversion=None,
            roas=None,
        )
    )
    session.add(
        ChangeEvent(
            account_id=account.id,
            resource_name=f"customers/{account.customer_id}/changeEvents/budget",
            event_timestamp=datetime.combine(as_of, datetime.min.time(), tzinfo=UTC),
            resource_type="CAMPAIGN_BUDGET",
            resource_changed_name=campaigns["Non-brand Search"].name,
            change_type="UPDATE",
            field_changed="amount_micros",
            old_value={"amount_micros": 200_000_000},
            new_value={"amount_micros": 250_000_000},
            client_type="GOOGLE_ADS_WEB_CLIENT",
            user_email=FIXTURE_EMAIL,
        )
    )
    account.last_successful_sync_at = datetime.now(UTC)
    session.flush()
    return {
        "email": FIXTURE_EMAIL,
        "user_id": user.id,
        "workspace_id": workspace.id,
        "account_id": account.id,
        "as_of": as_of.isoformat(),
    }
