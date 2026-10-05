from __future__ import annotations

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


def window_for(kind: str, as_of: date) -> tuple[tuple[date, date], tuple[date, date], str]:
    """Return current bounds, previous bounds, and normalization mode."""
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
