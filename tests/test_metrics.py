from datetime import date

import pytest
from gads_analytics.metrics import Totals, assert_equal_length, pct_change, ratio, window_for
from gads_ingestion.jobs import date_window, iter_chunks


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


def test_today_versus_yesterday_is_one_day_each():
    current, previous, normalization = window_for("today_vs_yesterday", date(2026, 10, 6))
    assert current == (date(2026, 10, 6), date(2026, 10, 6))
    assert previous == (date(2026, 10, 5), date(2026, 10, 5))
    assert normalization == "totals"


def test_yesterday_window_is_one_day_against_seven():
    current, previous, normalization = window_for("yesterday_vs_prev7_avg", date(2026, 9, 15))
    assert current == (date(2026, 9, 15), date(2026, 9, 15))
    assert previous == (date(2026, 9, 8), date(2026, 9, 14))
    assert normalization == "daily_average"


def test_seven_day_windows_match_length():
    current, previous, normalization = window_for("last_7_vs_prev_7", date(2026, 9, 15))
    assert (current[1] - current[0]).days == (previous[1] - previous[0]).days
    assert normalization == "totals"


def test_history_windows_cover_month_quarter_and_ninety_days():
    current, previous, normalization = window_for("last_90_vs_prev_90", date(2026, 9, 15))
    assert current == (date(2026, 6, 18), date(2026, 9, 15))
    assert (previous[1] - previous[0]).days == 89
    assert normalization == "totals"
    month_current, month_previous, _ = window_for("month_to_date_vs_prev", date(2026, 10, 5))
    assert month_current == (date(2026, 10, 1), date(2026, 10, 5))
    assert month_previous == (date(2026, 9, 1), date(2026, 9, 5))
    quarter_current, quarter_previous, _ = window_for("quarter_to_date_vs_prev", date(2026, 10, 5))
    assert quarter_current == (date(2026, 10, 1), date(2026, 10, 5))
    assert quarter_previous == (date(2026, 7, 1), date(2026, 7, 5))
    _, clamped_previous, _ = window_for("month_to_date_vs_prev", date(2026, 3, 31))
    assert clamped_previous == (date(2026, 2, 1), date(2026, 2, 28))


def test_all_time_uses_history_start_and_equal_prior_window():
    current, previous, normalization = window_for("all_time", date(2026, 9, 15), history_start=date(2026, 9, 2))
    assert current == (date(2026, 9, 2), date(2026, 9, 15))
    assert previous == (date(2026, 8, 19), date(2026, 9, 1))
    assert (current[1] - current[0]).days == (previous[1] - previous[0]).days
    assert normalization == "totals"
    alone_current, alone_previous, _ = window_for("all_time", date(2026, 9, 15))
    assert alone_current == (date(2026, 9, 15), date(2026, 9, 15))
    assert alone_previous == (date(2026, 9, 14), date(2026, 9, 14))


def test_history_sync_chunks_long_ranges():
    start, end = date_window("history", date(2026, 10, 6))
    assert (end - start).days + 1 == 395
    chunks = list(iter_chunks(start, end))
    assert chunks[0][0] == start
    assert chunks[-1][1] == end
    assert all((chunk_end - chunk_start).days + 1 <= 90 for chunk_start, chunk_end in chunks)
    assert len(chunks) == 5
