"""Google Ads ingestion workers. Jobs are idempotent and independent per dataset."""

DATASETS = (
    "campaigns",
    "ad_groups",
    "keywords",
    "ads",
    "campaign_daily",
    "ad_group_daily",
    "keyword_daily",
    "search_terms",
    "budgets",
    "change_events",
)
