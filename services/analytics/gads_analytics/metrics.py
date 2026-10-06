from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date, timedelta


def ratio(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator is None or denominator == 0:
        return None
    return numerator / denominator


def pct_change(current: float | None, baseline: float | None) -> float | None:
    if current is None or baseline is None or baseline == 0:
        return None
    return (current - baseline) / abs(baseline)


def money_from_micros(micros: float | int | None) -> float:
    if micros is None:
        return 0.0
    return round(float(micros) / 1_000_000, 6)


@dataclass
class Totals:
    impressions: float = 0
    clicks: float = 0
    cost: float = 0
    conversions: float = 0
    conversion_value: float = 0

    def add(self, other: Totals) -> Totals:
        return Totals(
            impressions=self.impressions + other.impressions,
            clicks=self.clicks + other.clicks,
            cost=self.cost + other.cost,
            conversions=self.conversions + other.conversions,
            conversion_value=self.conversion_value + other.conversion_value,
        )

    def scale(self, days: int) -> Totals:
        if days <= 0:
            return Totals()
        return Totals(
            impressions=self.impressions / days,
            clicks=self.clicks / days,
            cost=self.cost / days,
            conversions=self.conversions / days,
            conversion_value=self.conversion_value / days,
        )

    def derived(self) -> dict[str, float | None]:
        return {
            "ctr": ratio(self.clicks, self.impressions),
            "average_cpc": ratio(self.cost, self.clicks),
            "average_cpm": ratio(self.cost * 1000, self.impressions),
            "conversion_rate": ratio(self.conversions, self.clicks),
            "cost_per_conversion": ratio(self.cost, self.conversions),
            "roas": ratio(self.conversion_value, self.cost),
        }

    def as_dict(self) -> dict:
        payload = {
            "impressions": self.impressions,
            "clicks": self.clicks,
            "cost": round(self.cost, 6),
            "conversions": self.conversions,
            "conversion_value": round(self.conversion_value, 6),
        }
        payload.update(self.derived())
        return payload


def period_length(start: date, end: date) -> int:
    return (end - start).days + 1


def assert_equal_length(start: date, end: date, previous_start: date, previous_end: date) -> None:
    if period_length(start, end) != period_length(previous_start, previous_end):
        raise ValueError("Periods must be the same length unless a named comparison normalizes them")


def _shift_months(day: date, months: int) -> date:
    month_index = day.month - 1 + months
    year = day.year + month_index // 12
    month = month_index % 12 + 1
    return date(year, month, min(day.day, calendar.monthrange(year, month)[1]))


def window_for(
    kind: str,
    as_of: date,
    *,
    history_start: date | None = None,
) -> tuple[tuple[date, date], tuple[date, date], str]:
    """Return current bounds, previous bounds, and normalization mode."""
    if kind == "today_vs_yesterday":
        return (as_of, as_of), (as_of - timedelta(days=1), as_of - timedelta(days=1)), "totals"
    if kind == "yesterday_vs_prev7_avg":
        return (as_of, as_of), (as_of - timedelta(days=7), as_of - timedelta(days=1)), "daily_average"
    if kind == "yesterday_vs_same_weekday":
        previous = [as_of - timedelta(days=7 * week) for week in range(1, 5)]
        return (as_of, as_of), (previous[-1], previous[0]), "same_weekday"
    if kind == "last_7_vs_prev_7":
        return (as_of - timedelta(days=6), as_of), (as_of - timedelta(days=13), as_of - timedelta(days=7)), "totals"
    if kind == "last_14_vs_prev_14":
        return (as_of - timedelta(days=13), as_of), (as_of - timedelta(days=27), as_of - timedelta(days=14)), "totals"
    if kind == "last_30_vs_prev_30":
        return (as_of - timedelta(days=29), as_of), (as_of - timedelta(days=59), as_of - timedelta(days=30)), "totals"
    if kind == "last_90_vs_prev_90":
        return (as_of - timedelta(days=89), as_of), (as_of - timedelta(days=179), as_of - timedelta(days=90)), "totals"
    if kind == "month_to_date_vs_prev":
        previous = _shift_months(as_of, -1)
        return (as_of.replace(day=1), as_of), (previous.replace(day=1), previous), "totals"
    if kind == "quarter_to_date_vs_prev":
        start_month = ((as_of.month - 1) // 3) * 3 + 1
        current_start = date(as_of.year, start_month, 1)
        previous = _shift_months(as_of, -3)
        previous_start_month = ((previous.month - 1) // 3) * 3 + 1
        previous_start = date(previous.year, previous_start_month, 1)
        return (current_start, as_of), (previous_start, previous), "totals"
    if kind == "all_time":
        start = history_start or as_of
        if start > as_of:
            start = as_of
        days = (as_of - start).days + 1
        previous_end = start - timedelta(days=1)
        previous_start = previous_end - timedelta(days=days - 1)
        return (start, as_of), (previous_start, previous_end), "totals"
    raise ValueError(f"Unknown comparison kind: {kind}")


def same_weekday_dates(as_of: date, weeks: int = 4) -> list[date]:
    return [as_of - timedelta(days=7 * week) for week in range(1, weeks + 1)]


METRIC_KEYS = (
    "impressions",
    "clicks",
    "cost",
    "conversions",
    "conversion_value",
    "ctr",
    "average_cpc",
    "average_cpm",
    "conversion_rate",
    "cost_per_conversion",
    "roas",
)


def compare_metric_sets(current: dict, baseline: dict) -> dict:
    changes = {}
    for key in METRIC_KEYS:
        current_value = current.get(key)
        baseline_value = baseline.get(key)
        absolute = None
        if current_value is not None and baseline_value is not None:
            absolute = current_value - baseline_value
        changes[key] = {
            "absolute": absolute,
            "percent": pct_change(current_value, baseline_value),
        }
    return changes
