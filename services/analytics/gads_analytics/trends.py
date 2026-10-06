from __future__ import annotations

from collections import defaultdict
from datetime import date

from gads_analytics.analysis import compare_totals
from gads_analytics.metrics import Totals
from gads_analytics.repository import _by_campaign, _campaign_names, _rows_between, _sum_rows

# A move smaller than this is treated as flat, so one noisy day does not become a trend.
STEADY_PERCENT = 0.05

MOVEMENTS = (
    ("cost", "Spend", "either"),
    ("conversions", "Conversions", "up"),
    ("cost_per_conversion", "CPA", "down"),
    ("roas", "ROAS", "up"),
    ("average_cpc", "CPC", "down"),
    ("conversion_rate", "Conversion rate", "up"),
)


def _direction(percent: float | None, better: str) -> str:
    if percent is None or abs(percent) < STEADY_PERCENT:
        return "steady"
    if better == "either":
        return "up" if percent > 0 else "down"
    improved = percent > 0 if better == "up" else percent < 0
    return "improving" if improved else "worsening"


def _conversions(value: float) -> str:
    if float(value).is_integer():
        count = int(value)
        noun = "conversion" if abs(count) == 1 else "conversions"
        return f"{count} {noun}"
    return f"{float(value):.2f} conversions"


def _fmt(metric: str, value: float | None) -> str:
    if value is None:
        return "n/a"
    if metric == "conversion_rate":
        return f"{float(value):.1%}"
    number = float(value)
    if metric == "conversions" and number.is_integer():
        return str(int(number))
    return f"{number:.2f}"


def _pct(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{float(value):+.1%}"


def _movement_sentence(item: dict) -> str:
    label = item["label"]
    earlier = _fmt(item["metric"], item["earlier"])
    later = _fmt(item["metric"], item["later"])
    change = _pct(item["percent"])
    direction = item["direction"]
    if direction == "steady":
        return f"{label} held steady ({earlier} in the earlier half, {later} in the later half)."
    if direction in {"improving", "worsening"}:
        verb = "improved" if direction == "improving" else "worsened"
        return f"{label} {verb}, from {earlier} in the earlier half to {later} in the later half ({change})."
    verb = "rose" if direction == "up" else "fell"
    return f"{label} {verb} {change}, from {earlier} in the earlier half to {later} in the later half."


def _tension(movements: list[dict]) -> str | None:
    by_metric = {item["metric"]: item for item in movements}
    spend = by_metric.get("cost", {}).get("direction")
    conversions = by_metric.get("conversions", {}).get("direction")
    cpa = by_metric.get("cost_per_conversion", {}).get("direction")
    if spend == "up" and conversions == "down":
        return "Spend rose while conversions fell, so the later half paid more and got less."
    if spend == "down" and conversions == "up":
        return "Spend fell while conversions rose, so the later half got more from less money."
    if spend == "up" and conversions == "up" and cpa == "worsening":
        return "Spend and conversions both rose, and each conversion cost more in the later half."
    if spend == "down" and conversions == "down" and cpa == "improving":
        return "Spend and conversions both fell, and each conversion cost less in the later half."
    return None


def _campaign_sentences(campaigns: list[dict]) -> list[str]:
    lines = []
    for row in campaigns:
        if abs(row["spend_delta"]) < 1 and abs(row["conversion_delta"]) < 0.5:
            continue
        lines.append(
            f"{row['name']} moved from {_fmt('cost', row['earlier_cost'])} spend and "
            f"{_conversions(row['earlier_conversions'])} in the earlier half to "
            f"{_fmt('cost', row['later_cost'])} spend and {_conversions(row['later_conversions'])} in the later half."
        )
        if len(lines) == 3:
            break
    return lines


def strategy_context(trends: dict) -> dict:
    """Compact the daily series into weeks so a long-term question is not a list of single days."""
    weeks: dict[str, dict] = {}
    for point in trends["series"]:
        day = date.fromisoformat(point["date"])
        year, week, _weekday = day.isocalendar()
        key = f"{year}-W{week:02d}"
        bucket = weeks.get(key)
        if bucket is None:
            bucket = {
                "week": key,
                "start": point["date"],
                "end": point["date"],
                "cost": 0.0,
                "conversions": 0.0,
                "conversion_value": 0.0,
                "clicks": 0.0,
                "impressions": 0.0,
            }
            weeks[key] = bucket
        bucket["end"] = point["date"]
        for field in ("cost", "conversions", "conversion_value", "clicks", "impressions"):
            bucket[field] += float(point.get(field) or 0)
    weekly = []
    for bucket in weeks.values():
        cost = bucket["cost"]
        conversions = bucket["conversions"]
        clicks = bucket["clicks"]
        weekly.append(
            {
                "week": bucket["week"],
                "start": bucket["start"],
                "end": bucket["end"],
                "cost": round(cost, 2),
                "conversions": round(conversions, 2),
                "conversion_value": round(bucket["conversion_value"], 2),
                "clicks": round(clicks, 2),
                "impressions": round(bucket["impressions"], 2),
                "cpa": round(cost / conversions, 2) if conversions else None,
                "cpc": round(cost / clicks, 2) if clicks else None,
                "conversion_rate": round(conversions / clicks, 4) if clicks else None,
            }
        )
    account = trends["account"]
    return {
        "comparison": "earlier half of the selected period versus the later half, plus a weekly series",
        "period": {"start": trends["start_date"], "end": trends["end_date"], "days": trends["days"]},
        "earlier_half": trends["earlier"],
        "later_half": trends["later"],
        "totals": {
            key: account.get(key)
            for key in (
                "cost",
                "conversions",
                "conversion_value",
                "cost_per_conversion",
                "roas",
                "average_cpc",
                "conversion_rate",
                "clicks",
                "impressions",
            )
        },
        "half_comparison": trends["movements"],
        "campaigns": trends["campaigns"],
        "findings": trends["findings"],
        "weekly": weekly,
    }


def build_trends(session, account, start: date, end: date) -> dict:
    rows = _rows_between(session, account.id, start, end)
    by_day: dict[date, list] = defaultdict(list)
    for row in rows:
        by_day[row.date].append(row)
    days = sorted(by_day)
    series = []
    for day in days:
        point = _sum_rows(by_day[day]).as_dict()
        point["date"] = day.isoformat()
        series.append(point)

    half = len(days) // 2
    early_days = days[:half]
    late_days = days[-half:] if half else []
    early_rows = [row for day in early_days for row in by_day[day]]
    late_rows = [row for day in late_days for row in by_day[day]]
    compared = compare_totals(_sum_rows(late_rows), _sum_rows(early_rows)) if half else None
    movements = []
    if compared:
        for metric, label, better in MOVEMENTS:
            change = compared["changes"].get(metric) or {}
            percent = change.get("percent")
            movements.append(
                {
                    "metric": metric,
                    "label": label,
                    "better": better,
                    "earlier": compared["baseline"].get(metric),
                    "later": compared["current"].get(metric),
                    "percent": percent,
                    "direction": _direction(percent, better),
                }
            )

    names = _campaign_names(session, account.id)
    early_campaigns = _by_campaign(early_rows)
    late_campaigns = _by_campaign(late_rows)
    campaigns = []
    for campaign_id in set(early_campaigns) | set(late_campaigns):
        before = early_campaigns.get(campaign_id, Totals())
        now = late_campaigns.get(campaign_id, Totals())
        if before.cost == 0 and now.cost == 0 and before.conversions == 0 and now.conversions == 0:
            continue
        campaigns.append(
            {
                "campaign_id": campaign_id,
                "name": names.get(campaign_id, campaign_id),
                "earlier_cost": round(before.cost, 2),
                "later_cost": round(now.cost, 2),
                "spend_delta": round(now.cost - before.cost, 2),
                "earlier_conversions": before.conversions,
                "later_conversions": now.conversions,
                "conversion_delta": now.conversions - before.conversions,
            }
        )
    campaigns.sort(key=lambda item: abs(item["spend_delta"]), reverse=True)

    earlier = {
        "start": early_days[0].isoformat() if early_days else None,
        "end": early_days[-1].isoformat() if early_days else None,
    }
    later = {
        "start": late_days[0].isoformat() if late_days else None,
        "end": late_days[-1].isoformat() if late_days else None,
    }
    return {
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "days": len(days),
        "earlier": earlier,
        "later": later,
        "account": _sum_rows(rows).as_dict(),
        "series": series,
        "movements": movements,
        "campaigns": campaigns[:12],
        "findings": _findings(start, end, len(days), earlier, later, movements, campaigns),
    }


def _findings(
    start: date,
    end: date,
    day_count: int,
    earlier: dict,
    later: dict,
    movements: list[dict],
    campaigns: list[dict],
) -> list[str]:
    if day_count == 0:
        return [f"No daily campaign stats are stored from {start.isoformat()} to {end.isoformat()}."]
    if day_count < 2 or not earlier["start"] or not later["start"]:
        return [
            f"Only {day_count} day of campaign stats is stored from {start.isoformat()} to {end.isoformat()}, so there is no span to compare."
        ]
    lines = [
        f"Daily stats from {start.isoformat()} to {end.isoformat()} ({day_count} days) are split into an earlier half "
        f"({earlier['start']} to {earlier['end']}) and a later half ({later['start']} to {later['end']}). "
        "The comparison is those two halves, not each day against the day before."
    ]
    lines.extend(_movement_sentence(item) for item in movements)
    tension = _tension(movements)
    if tension:
        lines.append(tension)
    lines.extend(_campaign_sentences(campaigns))
    return lines
