from __future__ import annotations

from datetime import date, timedelta

MAX_INGEST_DAYS = 400
CHANGE_EVENT_LIMIT = 10000
CHANGE_EVENT_RETENTION_DAYS = 30


def validate_range(start: date, end: date, max_days: int = MAX_INGEST_DAYS) -> None:
    if not isinstance(start, date) or not isinstance(end, date):
        raise TypeError("start and end must be dates")
    if end < start:
        raise ValueError("end date is before start date")
    if (end - start).days + 1 > max_days:
        raise ValueError(f"Date range exceeds {max_days} days")


def _iso(value: date) -> str:
    if value.isoformat() != value.strftime("%Y-%m-%d"):
        raise ValueError("Invalid date")
    return value.isoformat()


def campaigns_query() -> str:
    return """
SELECT
  campaign.id,
  campaign.name,
  campaign.status,
  campaign.advertising_channel_type,
  campaign.advertising_channel_sub_type,
  campaign.start_date,
  campaign.end_date,
  campaign.resource_name,
  campaign_budget.amount_micros
FROM campaign
""".strip()


def ad_groups_query() -> str:
    return """
SELECT
  ad_group.id,
  ad_group.name,
  ad_group.status,
  ad_group.type,
  ad_group.resource_name,
  campaign.id
FROM ad_group
""".strip()


def keywords_query() -> str:
    return """
SELECT
  ad_group_criterion.criterion_id,
  ad_group_criterion.keyword.text,
  ad_group_criterion.keyword.match_type,
  ad_group_criterion.status,
  ad_group_criterion.quality_info.quality_score,
  ad_group_criterion.resource_name,
  ad_group.id,
  campaign.id
FROM keyword_view
""".strip()


def ads_query() -> str:
    return """
SELECT
  ad_group_ad.ad.id,
  ad_group_ad.ad.type,
  ad_group_ad.ad.final_urls,
  ad_group_ad.ad.responsive_search_ad.headlines,
  ad_group_ad.ad.responsive_search_ad.descriptions,
  ad_group_ad.ad.resource_name,
  ad_group_ad.status,
  ad_group.id,
  campaign.id
FROM ad_group_ad
""".strip()


def _metrics(extra: str = "") -> str:
    return f"""
  metrics.impressions,
  metrics.clicks,
  metrics.cost_micros,
  metrics.conversions,
  metrics.conversions_value{extra}
""".rstrip()


def campaign_metrics_query(start: date, end: date) -> str:
    validate_range(start, end)
    return f"""
SELECT
  campaign.id,
  campaign.resource_name,
  segments.date,
{_metrics(''',
  metrics.search_impression_share,
  metrics.search_budget_lost_impression_share,
  metrics.search_rank_lost_impression_share''')}
FROM campaign
WHERE segments.date BETWEEN '{_iso(start)}' AND '{_iso(end)}'
""".strip()


def ad_group_metrics_query(start: date, end: date) -> str:
    validate_range(start, end)
    return f"""
SELECT
  ad_group.id,
  campaign.id,
  segments.date,
{_metrics()}
FROM ad_group
WHERE segments.date BETWEEN '{_iso(start)}' AND '{_iso(end)}'
""".strip()


def keyword_metrics_query(start: date, end: date) -> str:
    validate_range(start, end)
    return f"""
SELECT
  ad_group_criterion.criterion_id,
  ad_group.id,
  campaign.id,
  segments.date,
{_metrics()}
FROM keyword_view
WHERE segments.date BETWEEN '{_iso(start)}' AND '{_iso(end)}'
""".strip()


def search_terms_query(start: date, end: date) -> str:
    validate_range(start, end)
    return f"""
SELECT
  search_term_view.search_term,
  search_term_view.resource_name,
  segments.date,
  segments.keyword.ad_group_criterion,
  segments.search_term_match_type,
  campaign.id,
  ad_group.id,
{_metrics()}
FROM search_term_view
WHERE segments.date BETWEEN '{_iso(start)}' AND '{_iso(end)}'
""".strip()


def campaign_search_terms_query(start: date, end: date) -> str:
    validate_range(start, end)
    return f"""
SELECT
  campaign_search_term_view.search_term,
  campaign_search_term_view.resource_name,
  segments.date,
  campaign.id,
{_metrics()}
FROM campaign_search_term_view
WHERE segments.date BETWEEN '{_iso(start)}' AND '{_iso(end)}'
""".strip()


def budgets_query(start: date, end: date) -> str:
    validate_range(start, end)
    return f"""
SELECT
  campaign.id,
  campaign.resource_name,
  segments.date,
  campaign_budget.amount_micros,
  metrics.cost_micros,
  metrics.impressions,
  metrics.search_budget_lost_impression_share
FROM campaign
WHERE segments.date BETWEEN '{_iso(start)}' AND '{_iso(end)}'
""".strip()


def clamp_change_window(start: date, end: date, today: date | None = None) -> tuple[date, date]:
    today = today or date.today()
    earliest = today - timedelta(days=CHANGE_EVENT_RETENTION_DAYS - 1)
    clamped_start = max(start, earliest)
    clamped_end = min(end, today)
    if clamped_start > clamped_end:
        raise ValueError("Change events are only available for the past 30 days")
    return clamped_start, clamped_end


def change_events_query(start: date, end: date, today: date | None = None) -> str:
    clamped_start, clamped_end = clamp_change_window(start, end, today)
    return f"""
SELECT
  change_event.resource_name,
  change_event.change_date_time,
  change_event.change_resource_name,
  change_event.change_resource_type,
  change_event.user_email,
  change_event.client_type,
  change_event.resource_change_operation,
  change_event.changed_fields,
  change_event.old_resource,
  change_event.new_resource
FROM change_event
WHERE change_event.change_date_time >= '{_iso(clamped_start)}'
  AND change_event.change_date_time <= '{_iso(clamped_end)} 23:59:59'
ORDER BY change_event.change_date_time DESC
LIMIT {CHANGE_EVENT_LIMIT}
""".strip()


def customer_query() -> str:
    return """
SELECT
  customer.id,
  customer.descriptive_name,
  customer.currency_code,
  customer.time_zone,
  customer.manager,
  customer.status
FROM customer
LIMIT 1
""".strip()


def customer_clients_query() -> str:
    return """
SELECT
  customer_client.client_customer,
  customer_client.id,
  customer_client.descriptive_name,
  customer_client.currency_code,
  customer_client.time_zone,
  customer_client.manager,
  customer_client.status,
  customer_client.level
FROM customer_client
WHERE customer_client.level <= 1
""".strip()
