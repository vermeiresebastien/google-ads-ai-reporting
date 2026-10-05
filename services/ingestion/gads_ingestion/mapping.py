from __future__ import annotations

from datetime import UTC, date, datetime

from gads_analytics.metrics import money_from_micros, ratio


def num(value, default=0.0) -> float:
    if value is None or value == "":
        return default
    return float(value)


def optional_num(value) -> float | None:
    if value is None or value == "":
        return None
    return float(value)


def text_id(value) -> str:
    if value is None:
        return ""
    return str(value)


def parse_date(value: str | None) -> date | None:
    if not value or value.startswith("2037"):
        return None
    return date.fromisoformat(value[:10])


def parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    cleaned = value.replace("Z", "+00:00")
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(cleaned[:19], fmt).replace(tzinfo=UTC)
        except ValueError:
            continue
    parsed = datetime.fromisoformat(cleaned)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed


def derived_metrics(impressions: float, clicks: float, cost: float, conversions: float, conversion_value: float) -> dict:
    return {
        "ctr": ratio(clicks, impressions),
        "average_cpc": ratio(cost, clicks),
        "average_cpm": ratio(cost * 1000, impressions) if impressions else None,
        "conversion_rate": ratio(conversions, clicks),
        "cost_per_conversion": ratio(cost, conversions),
        "roas": ratio(conversion_value, cost),
    }


def metric_block(metrics: dict | None) -> dict:
    metrics = metrics or {}
    impressions = int(num(metrics.get("impressions")))
    clicks = int(num(metrics.get("clicks")))
    cost_micros = int(num(metrics.get("cost_micros")))
    cost = money_from_micros(cost_micros)
    conversions = num(metrics.get("conversions"))
    conversion_value = num(metrics.get("conversions_value"))
    payload = {
        "impressions": impressions,
        "clicks": clicks,
        "cost_micros": cost_micros,
        "cost": cost,
        "conversions": conversions,
        "conversion_value": conversion_value,
    }
    payload.update(derived_metrics(impressions, clicks, cost, conversions, conversion_value))
    return payload
