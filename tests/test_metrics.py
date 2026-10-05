from datetime import date

import pytest
from gads_analytics.metrics import Totals, assert_equal_length, pct_change, ratio, window_for


def test_ratio_protects_divide_by_zero():
    assert ratio(1, 0) is None
    assert ratio(1, None) is None
    assert ratio(10, 4) == 2.5


def test_percent_change():
    assert pct_change(110, 100) == pytest.approx(0.1)
    assert pct_change(5, 0) is None
    assert pct_change(None, 10) is None


def test_derived_metrics():
    metrics = Totals(impressions=1000, clicks=100, cost=250, conversions=10, conversion_value=500).as_dict()
    assert metrics["ctr"] == pytest.approx(0.1)
    assert metrics["average_cpc"] == pytest.approx(2.5)
    assert metrics["conversion_rate"] == pytest.approx(0.1)
    assert metrics["cost_per_conversion"] == pytest.approx(25)
    assert metrics["roas"] == pytest.approx(2)


def test_zero_conversion_cpa_is_undefined():
    metrics = Totals(impressions=10, clicks=2, cost=40, conversions=0, conversion_value=0).derived()
    assert metrics["cost_per_conversion"] is None
    assert metrics["roas"] == 0 or metrics["roas"] is None or metrics["roas"] == pytest.approx(0)


def test_equal_length_guard():
    with pytest.raises(ValueError):
        assert_equal_length(date(2026, 9, 1), date(2026, 9, 7), date(2026, 8, 1), date(2026, 8, 30))


def test_yesterday_window_is_one_day_against_seven():
    current, previous, normalization = window_for("yesterday_vs_prev7_avg", date(2026, 9, 15))
    assert current == (date(2026, 9, 15), date(2026, 9, 15))
    assert previous == (date(2026, 9, 8), date(2026, 9, 14))
    assert normalization == "daily_average"


def test_seven_day_windows_match_length():
    current, previous, normalization = window_for("last_7_vs_prev_7", date(2026, 9, 15))
    assert (current[1] - current[0]).days == (previous[1] - previous[0]).days
    assert normalization == "totals"
