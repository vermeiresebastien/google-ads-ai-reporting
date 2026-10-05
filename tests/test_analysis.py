from gads_analytics.analysis import (
    Thresholds,
    budget_opportunities,
    campaign_drivers,
    detect_anomalies,
    wasted_spend_candidates,
)
from gads_analytics.metrics import Totals


def test_spend_anomaly_respects_threshold():
    thresholds = Thresholds(spend_anomaly_pct=0.3, min_spend_for_anomaly=10)
    current = Totals(cost=150, clicks=20, impressions=100, conversions=5, conversion_value=100)
    baseline = Totals(cost=100, clicks=20, impressions=100, conversions=5, conversion_value=100)
    kinds = {item["type"] for item in detect_anomalies(current, baseline, thresholds)}
    assert "spend_anomaly" in kinds


def test_small_spend_is_not_an_anomaly():
    thresholds = Thresholds(min_spend_for_anomaly=50, spend_anomaly_pct=0.3)
    current = Totals(cost=10, clicks=2, impressions=10, conversions=1, conversion_value=5)
    baseline = Totals(cost=4, clicks=2, impressions=10, conversions=1, conversion_value=5)
    assert detect_anomalies(current, baseline, thresholds) == []


def test_waste_requires_spend_and_clicks():
    thresholds = Thresholds(min_spend_for_waste=50, zero_conversion_min_spend=25, min_clicks=10)
    rows = [
        {"kind": "search_term", "name": "cheap", "totals": Totals(cost=10, clicks=20, impressions=100)},
        {"kind": "search_term", "name": "free competitor alternative", "totals": Totals(cost=80, clicks=30, impressions=200)},
    ]
    found = wasted_spend_candidates(rows, thresholds, account_cpa=20)
    assert [item["name"] for item in found] == ["free competitor alternative"]
    assert found[0]["label"] == "candidate"


def test_budget_opportunity_needs_performance_evidence():
    thresholds = Thresholds(budget_lost_is_min=0.15, min_spend_for_anomaly=20)
    account = Totals(cost=100, conversions=10, clicks=40, impressions=200, conversion_value=200)
    campaigns = [
        {
            "campaign_id": "good",
            "name": "Prospecting Exact",
            "totals": Totals(cost=50, conversions=10, clicks=20, impressions=100, conversion_value=200),
            "budget_lost_impression_share": 0.4,
        },
        {
            "campaign_id": "weak",
            "name": "Weak",
            "totals": Totals(cost=50, conversions=1, clicks=20, impressions=100, conversion_value=1),
            "budget_lost_impression_share": 0.4,
        },
        {
            "campaign_id": "unconstrained",
            "name": "Brand",
            "totals": Totals(cost=50, conversions=10, clicks=20, impressions=100, conversion_value=200),
            "budget_lost_impression_share": 0.02,
        },
    ]
    names = [item["name"] for item in budget_opportunities(campaigns, thresholds, account)]
    assert names == ["Prospecting Exact"]


def test_drivers_rank_the_campaign_that_got_less_efficient():
    current = {"nb": Totals(cost=230, conversions=6, clicks=70, impressions=300, conversion_value=240)}
    previous = {"nb": Totals(cost=200, conversions=8, clicks=80, impressions=400, conversion_value=320)}
    drivers = campaign_drivers(current, previous, {"nb": "Non-brand Search"})
    assert drivers["increased_cpa"][0]["name"] == "Non-brand Search"
    assert drivers["lost_conversions"][0]["conversion_delta"] == -2
