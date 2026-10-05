from datetime import date

import pytest
from gads_ingestion.google_ads.queries import (
    campaign_metrics_query,
    campaigns_query,
    change_events_query,
    search_terms_query,
)


def test_queries_are_parameterized_dates_without_injection():
    query = campaign_metrics_query(date(2026, 9, 1), date(2026, 9, 7))
    assert "2026-09-01" in query
    assert "2026-09-07" in query
    assert ";" not in query
    assert "DROP" not in query
    assert "FROM campaign" in campaigns_query()


def test_change_events_require_limit_and_recent_window():
    query = change_events_query(date(2026, 9, 1), date(2026, 9, 10), today=date(2026, 9, 10))
    assert "LIMIT 10000" in query
    assert "change_event.change_date_time" in query
    with pytest.raises(ValueError):
        change_events_query(date(2020, 1, 1), date(2020, 1, 5), today=date(2026, 9, 10))


def test_inverted_range_is_rejected():
    with pytest.raises(ValueError):
        search_terms_query(date(2026, 9, 8), date(2026, 9, 1))


def test_search_terms_include_pmax_resource_separately():
    from gads_ingestion.google_ads.queries import campaign_search_terms_query

    query = campaign_search_terms_query(date(2026, 9, 1), date(2026, 9, 2))
    assert "FROM campaign_search_term_view" in query
    assert "FROM search_term_view" not in query
