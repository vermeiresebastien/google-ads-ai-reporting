from __future__ import annotations

import os

import httpx

try:
    from mcp.server.fastmcp import FastMCP
except ImportError:  # pragma: no cover - exercised only when the extra is missing
    FastMCP = None


def _base_url() -> str:
    return os.environ.get("GADS_API_BASE_URL", "http://localhost:8000").rstrip("/")


def _token() -> str:
    token = os.environ.get("GADS_API_TOKEN", "")
    if not token:
        raise RuntimeError("GADS_API_TOKEN is not configured")
    return token


def _request(method: str, path: str, **kwargs):
    response = httpx.request(
        method,
        f"{_base_url()}{path}",
        headers={"Authorization": f"Bearer {_token()}"},
        timeout=60,
        **kwargs,
    )
    response.raise_for_status()
    return response.json()


def _get(path: str, params: dict | None = None):
    cleaned = {key: value for key, value in (params or {}).items() if value is not None}
    return _request("GET", path, params=cleaned)


def build_server():
    if FastMCP is None:
        raise RuntimeError("The mcp package is not installed")
    mcp = FastMCP("gads-analyst")

    @mcp.tool()
    def get_account_summary(account_id: str, start_date: str | None = None, end_date: str | None = None) -> dict:
        """Account totals for a bounded date range. Requires access to the account."""
        return _get("/api/summary", {"account_id": account_id, "start_date": start_date, "end_date": end_date})

    @mcp.tool()
    def get_daily_report(account_id: str, as_of: str | None = None) -> dict:
        """Canonical daily report: yesterday versus the previous 7-day average."""
        return _get("/api/reports/daily", {"account_id": account_id, "as_of": as_of})

    @mcp.tool()
    def compare_periods(account_id: str, kind: str = "last_7_vs_prev_7", as_of: str | None = None) -> dict:
        """Compare periods. kind is yesterday_vs_prev7_avg, last_7_vs_prev_7, last_14_vs_prev_14, last_30_vs_prev_30, last_90_vs_prev_90, month_to_date_vs_prev, or quarter_to_date_vs_prev."""
        return _get("/api/compare", {"account_id": account_id, "kind": kind, "as_of": as_of})

    @mcp.tool()
    def get_campaign_performance(account_id: str, start_date: str | None = None, end_date: str | None = None) -> dict:
        """Campaign metrics for a bounded range, ordered by spend."""
        return _get("/api/campaigns", {"account_id": account_id, "start_date": start_date, "end_date": end_date})

    @mcp.tool()
    def get_campaign_detail(account_id: str, campaign_id: str) -> dict:
        """Metadata for one campaign in an account the caller can access."""
        return _get(f"/api/campaigns/{campaign_id}", {"account_id": account_id})

    @mcp.tool()
    def get_campaign_drivers(account_id: str, kind: str = "last_7_vs_prev_7", as_of: str | None = None) -> dict:
        """Campaigns that contributed most to spend, conversion, CPA, and value changes."""
        return _get("/api/campaign-drivers", {"account_id": account_id, "kind": kind, "as_of": as_of})

    @mcp.tool()
    def get_anomalies(account_id: str, kind: str = "yesterday_vs_prev7_avg", as_of: str | None = None) -> dict:
        """Deterministic anomalies versus the selected baseline."""
        return _get("/api/anomalies", {"account_id": account_id, "kind": kind, "as_of": as_of})

    @mcp.tool()
    def get_search_term_waste(account_id: str, start_date: str | None = None, end_date: str | None = None) -> dict:
        """Search terms and keywords that meet the configured waste thresholds."""
        return _get("/api/wasted-spend", {"account_id": account_id, "start_date": start_date, "end_date": end_date})

    @mcp.tool()
    def get_top_search_terms(account_id: str, start_date: str | None = None, end_date: str | None = None) -> dict:
        """Top search terms by spend. Results are row-limited."""
        return _get("/api/search-terms", {"account_id": account_id, "start_date": start_date, "end_date": end_date})

    @mcp.tool()
    def get_keyword_performance(account_id: str, start_date: str | None = None, end_date: str | None = None) -> dict:
        """Keyword metrics for a bounded range, ordered by spend."""
        return _get("/api/keywords", {"account_id": account_id, "start_date": start_date, "end_date": end_date})

    @mcp.tool()
    def get_budget_opportunities(account_id: str, start_date: str | None = None, end_date: str | None = None) -> dict:
        """Campaigns limited by budget that also have acceptable efficiency."""
        return _get("/api/budget-opportunities", {"account_id": account_id, "start_date": start_date, "end_date": end_date})

    @mcp.tool()
    def get_recent_changes(account_id: str, start_date: str | None = None, end_date: str | None = None) -> dict:
        """Recent Google Ads change events stored for the account."""
        return _get("/api/changes", {"account_id": account_id, "start_date": start_date, "end_date": end_date})

    return mcp


def main() -> None:
    build_server().run()


if __name__ == "__main__":
    main()
