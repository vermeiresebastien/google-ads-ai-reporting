from datetime import date

from gads.models import AdAccount
from gads_analytics.narrative import render_report
from gads_analytics.repository import build_report
from report_fixture import seed_report_account


REQUIRED_HEADINGS = [
    "## Executive summary",
    "## Performance",
    "## What changed",
    "## Why it changed",
    "## Problems",
    "## Opportunities",
    "## Recommended actions",
]


def test_render_report_follows_spec_structure_and_core_metrics(session):
    payload = seed_report_account(session, date(2026, 9, 15))
    account = session.get(AdAccount, payload["account_id"])
    report = build_report(session, account, "yesterday_vs_prev7_avg", date(2026, 9, 15))
    text = render_report(report)

    for heading in REQUIRED_HEADINGS:
        assert heading in text

    assert "conversion value" in text.lower()
    assert "Data freshness:" in text
    assert "Spend:" in text or "spend was" in text.lower()
    assert "CPA" in text
    assert "ROAS" in text
    assert "Hypothesis:" in text
    assert report["comparison"]["changes"]["conversion_value"] is not None


def test_render_report_includes_evidence_claims_when_present():
    text = render_report(
        {
            "date": "2026-09-15",
            "account": {
                "cost": 100,
                "conversions": 10,
                "conversion_value": 400,
                "cost_per_conversion": 10,
                "roas": 4,
            },
            "comparison": {
                "current": {
                    "cost": 100,
                    "conversions": 10,
                    "conversion_value": 400,
                    "cost_per_conversion": 10,
                    "roas": 4,
                    "average_cpc": 1,
                    "conversion_rate": 0.1,
                },
                "baseline": {
                    "cost": 80,
                    "conversions": 12,
                    "conversion_value": 480,
                    "cost_per_conversion": 6.67,
                    "roas": 6,
                    "average_cpc": 0.8,
                    "conversion_rate": 0.12,
                },
                "changes": {
                    "cost": {"percent": 0.25},
                    "conversions": {"percent": -0.17},
                    "conversion_value": {"percent": -0.17},
                    "cost_per_conversion": {"percent": 0.5},
                    "roas": {"percent": -0.33},
                    "average_cpc": {"percent": 0.25},
                    "conversion_rate": {"percent": -0.17},
                },
                "period": {
                    "current_start": "2026-09-15",
                    "current_end": "2026-09-15",
                    "baseline_start": "2026-09-08",
                    "baseline_end": "2026-09-14",
                    "normalization": "daily_average",
                },
            },
            "data_freshness": {"last_successful_sync": "2026-09-15T12:00:00+00:00"},
            "evidence": [
                {
                    "claim": "Account performance moved relative to the comparison baseline.",
                    "evidence": ["Spend changed 25.0%", "CPA changed 50.0%"],
                    "confidence": "high",
                }
            ],
            "top_changes": [],
            "campaign_drivers": {
                "increased_cpa": [
                    {
                        "campaign_id": "c1",
                        "name": "Non-brand Search",
                        "spend_delta": 30,
                        "conversion_delta": -2,
                        "value_delta": -80,
                        "current": {"average_cpc": 1.2, "conversion_rate": 0.08},
                        "previous": {"average_cpc": 1.0, "conversion_rate": 0.1},
                    }
                ],
                "lost_conversions": [],
                "increased_spend": [],
                "reduced_conversion_value": [],
            },
            "anomalies": [],
            "wasted_spend": [],
            "budget_opportunities": [],
            "recommended_actions": [
                {
                    "action": "Review Non-brand Search before raising budget.",
                    "evidence": ["CPA pressure is concentrated in one campaign"],
                    "confidence": "medium",
                }
            ],
            "recent_changes": [],
        }
    )
    assert "Claim (high confidence):" in text
    assert "Evidence: Spend changed 25.0%" in text
    assert "CPA-pressure campaign" in text
    assert "(medium confidence)" in text
    assert "Conversion value: current 400" in text
