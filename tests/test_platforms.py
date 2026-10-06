from gads.platforms import account_public, platform_spec
from gads_api.platform_oauth import PROVIDERS, authorization_url


def test_search_platforms_keep_search_terms():
    google = platform_spec("google")
    microsoft = platform_spec("microsoft")
    assert google.label == "Google Ads"
    assert google.search_terms is True
    assert google.changes is True
    assert google.sync_ready is True
    assert microsoft.search_terms is True
    assert microsoft.changes is False
    assert microsoft.sync_ready is False


def test_social_platforms_use_the_shared_reports_only():
    for name in ("meta", "linkedin", "x", "reddit"):
        spec = platform_spec(name)
        assert spec.search_terms is False
        assert spec.changes is False
        assert spec.sync_ready is False


def test_account_payload_names_the_platform():
    class Row:
        id = "acc"
        workspace_id = "ws"
        platform = "meta"
        customer_id = "act_1"
        manager_customer_id = None
        account_name = "Reducd"
        currency_code = "EUR"
        timezone = "Europe/Brussels"
        status = "ENABLED"
        last_successful_sync_at = None

    payload = account_public(Row())
    assert payload["platform"] == "meta"
    assert payload["platform_label"] == "Meta"
    assert payload["search_terms"] is False
    assert payload["changes"] is False
    assert payload["sync_ready"] is False


def test_each_extra_platform_has_an_oauth_provider():
    assert set(PROVIDERS) == {"microsoft", "meta", "linkedin", "x", "reddit"}
    url = authorization_url("meta", "state-token")
    assert "facebook.com" in url
    assert "state-token" in url
