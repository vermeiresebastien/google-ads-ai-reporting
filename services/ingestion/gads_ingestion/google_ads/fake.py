from __future__ import annotations


class FakeGoogleAdsClient:
    """In-memory Google Ads client used by tests."""

    def __init__(self, fixtures: dict | None = None):
        self.fixtures = fixtures or default_fixtures()

    def list_accessible_customers(self) -> list[str]:
        return list(self.fixtures.get("accessible", ["customers/1234567890"]))

    def search(self, customer_id: str, query: str) -> list[dict]:
        compact = " ".join(query.split())
        if "FROM customer_client" in compact:
            return list(self.fixtures.get("customer_clients", []))
        if "FROM customer " in compact or compact.endswith("FROM customer"):
            return list(self.fixtures.get("customers", []))
        if "FROM change_event" in compact:
            return list(self.fixtures.get("change_events", []))
        if "FROM campaign_search_term_view" in compact:
            return list(self.fixtures.get("campaign_search_terms", []))
        if "FROM search_term_view" in compact:
            return list(self.fixtures.get("search_terms", []))
        if "FROM keyword_view" in compact and "segments.date" in compact:
            return list(self.fixtures.get("keyword_daily", []))
        if "FROM keyword_view" in compact:
            return list(self.fixtures.get("keywords", []))
        if "FROM ad_group_ad" in compact:
            return list(self.fixtures.get("ads", []))
        if "FROM ad_group" in compact and "segments.date" in compact:
            return list(self.fixtures.get("ad_group_daily", []))
        if "FROM ad_group" in compact:
            return list(self.fixtures.get("ad_groups", []))
        if "FROM campaign" in compact and "campaign_budget.amount_micros" in compact and "segments.date" in compact:
            return list(self.fixtures.get("budgets", []))
        if "FROM campaign" in compact and "segments.date" in compact:
            return list(self.fixtures.get("campaign_daily", []))
        if "FROM campaign" in compact:
            return list(self.fixtures.get("campaigns", []))
        return []


def default_fixtures() -> dict:
    campaign = {
        "campaign": {
            "id": "111",
            "name": "Brand Search",
            "status": "ENABLED",
            "advertising_channel_type": "SEARCH",
            "advertising_channel_sub_type": "UNSPECIFIED",
            "start_date_time": "2026-01-01 00:00:00",
            "end_date_time": "2037-12-30 23:59:59",
            "resource_name": "customers/1234567890/campaigns/111",
        },
        "campaign_budget": {"amount_micros": "50000000"},
    }
    daily = {
        "campaign": {"id": "111", "resource_name": "customers/1234567890/campaigns/111"},
        "segments": {"date": "2026-09-01"},
        "metrics": {
            "impressions": "1000",
            "clicks": "100",
            "cost_micros": "250000000",
            "conversions": 10,
            "conversions_value": 500,
            "search_impression_share": 0.8,
            "search_budget_lost_impression_share": 0.05,
            "search_rank_lost_impression_share": 0.1,
        },
    }
    return {
        "accessible": ["customers/1234567890"],
        "customers": [
            {
                "customer": {
                    "id": "1234567890",
                    "descriptive_name": "Demo account",
                    "currency_code": "EUR",
                    "time_zone": "Europe/Brussels",
                    "manager": False,
                    "status": "ENABLED",
                }
            }
        ],
        "customer_clients": [],
        "campaigns": [campaign],
        "ad_groups": [
            {
                "ad_group": {
                    "id": "222",
                    "name": "Brand exact",
                    "status": "ENABLED",
                    "type": "SEARCH_STANDARD",
                    "resource_name": "customers/1234567890/adGroups/222",
                },
                "campaign": {"id": "111"},
            }
        ],
        "keywords": [
            {
                "ad_group_criterion": {
                    "criterion_id": "333",
                    "status": "ENABLED",
                    "resource_name": "customers/1234567890/adGroupCriteria/222~333",
                    "keyword": {"text": "brand name", "match_type": "EXACT"},
                    "quality_info": {"quality_score": 8},
                },
                "ad_group": {"id": "222"},
                "campaign": {"id": "111"},
            }
        ],
        "ads": [
            {
                "ad_group_ad": {
                    "status": "ENABLED",
                    "ad": {
                        "id": "444",
                        "type": "RESPONSIVE_SEARCH_AD",
                        "final_urls": ["https://example.com"],
                        "resource_name": "customers/1234567890/ads/444",
                        "responsive_search_ad": {
                            "headlines": [{"text": "Brand"}],
                            "descriptions": [{"text": "Official site"}],
                        },
                    },
                },
                "ad_group": {"id": "222"},
                "campaign": {"id": "111"},
            }
        ],
        "campaign_daily": [daily],
        "ad_group_daily": [
            {
                "ad_group": {"id": "222"},
                "campaign": {"id": "111"},
                "segments": {"date": "2026-09-01"},
                "metrics": {
                    "impressions": "1000",
                    "clicks": "100",
                    "cost_micros": "250000000",
                    "conversions": 10,
                    "conversions_value": 500,
                },
            }
        ],
        "keyword_daily": [
            {
                "ad_group_criterion": {"criterion_id": "333"},
                "ad_group": {"id": "222"},
                "campaign": {"id": "111"},
                "segments": {"date": "2026-09-01"},
                "metrics": {
                    "impressions": "800",
                    "clicks": "80",
                    "cost_micros": "200000000",
                    "conversions": 8,
                    "conversions_value": 400,
                },
            }
        ],
        "search_terms": [
            {
                "search_term_view": {
                    "search_term": "brand name",
                    "resource_name": "customers/1234567890/searchTermViews/1",
                },
                "segments": {
                    "date": "2026-09-01",
                    "keyword": {"ad_group_criterion": "customers/1234567890/adGroupCriteria/222~333"},
                    "search_term_match_type": "EXACT",
                },
                "campaign": {"id": "111"},
                "ad_group": {"id": "222"},
                "metrics": {
                    "impressions": "100",
                    "clicks": "20",
                    "cost_micros": "40000000",
                    "conversions": 4,
                    "conversions_value": 200,
                },
            }
        ],
        "campaign_search_terms": [
            {
                "campaign_search_term_view": {
                    "search_term": "pmax query",
                    "resource_name": "customers/1234567890/campaignSearchTermViews/9",
                },
                "segments": {"date": "2026-09-01"},
                "campaign": {"id": "111"},
                "metrics": {
                    "impressions": "50",
                    "clicks": "5",
                    "cost_micros": "10000000",
                    "conversions": 0,
                    "conversions_value": 0,
                },
            }
        ],
        "budgets": [
            {
                "campaign": {"id": "111", "resource_name": "customers/1234567890/campaigns/111"},
                "segments": {"date": "2026-09-01"},
                "campaign_budget": {"amount_micros": "50000000"},
                "metrics": {
                    "cost_micros": "250000000",
                    "impressions": "1000",
                    "search_budget_lost_impression_share": 0.05,
                },
            }
        ],
        "change_events": [
            {
                "change_event": {
                    "resource_name": "customers/1234567890/changeEvents/1~0~0",
                    "change_date_time": "2026-09-01 10:00:00",
                    "change_resource_name": "customers/1234567890/campaigns/111",
                    "change_resource_type": "CAMPAIGN",
                    "user_email": "ads@example.com",
                    "client_type": "GOOGLE_ADS_WEB_CLIENT",
                    "resource_change_operation": "UPDATE",
                    "changed_fields": "campaign.status",
                    "old_resource": {"campaign": {"status": "PAUSED"}},
                    "new_resource": {"campaign": {"status": "ENABLED"}},
                }
            }
        ],
    }
