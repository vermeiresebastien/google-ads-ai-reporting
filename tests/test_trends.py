import io
import zipfile
from datetime import date

from gads.models import AdAccount
from gads_analytics.ask import answer_strategy
from gads_analytics.council import CouncilRateLimited
from gads_analytics.saved_reports import (
    list_saved_reports,
    rename_saved_report,
    save_trend_summary,
    trend_notes_zip,
)
from gads_analytics.trends import build_trends, strategy_context
from report_fixture import seed_report_account


def test_trends_compare_halves_of_the_daily_stats(session):
    seeded = seed_report_account(session, date(2026, 9, 15))
    account = session.get(AdAccount, seeded["account_id"])
    payload = build_trends(session, account, date(2026, 9, 2), date(2026, 9, 15))

    assert payload["days"] == 14
    assert payload["earlier"] == {"start": "2026-09-02", "end": "2026-09-08"}
    assert payload["later"] == {"start": "2026-09-09", "end": "2026-09-15"}
    spend = next(item for item in payload["movements"] if item["metric"] == "cost")
    assert spend["later"] > spend["earlier"]
    assert "not each day against the day before" in payload["findings"][0]
    assert any("Non-brand Search" in line for line in payload["findings"])
    assert payload["series"][0]["date"] == "2026-09-02"
    assert payload["series"][-1]["date"] == "2026-09-15"


def test_strategy_context_rolls_days_into_weeks(session):
    seeded = seed_report_account(session, date(2026, 9, 15))
    account = session.get(AdAccount, seeded["account_id"])
    payload = build_trends(session, account, date(2026, 9, 2), date(2026, 9, 15))
    context = strategy_context(payload)

    assert context["comparison"].startswith("earlier half")
    assert len(context["weekly"]) >= 2
    assert len(context["weekly"]) < payload["days"]
    assert sum(week["cost"] for week in context["weekly"]) == round(payload["account"]["cost"], 2)


def test_strategy_answer_uses_the_trend_without_a_model(session, monkeypatch):
    seeded = seed_report_account(session, date(2026, 9, 15))
    account = session.get(AdAccount, seeded["account_id"])

    class _Settings:
        openrouter_api_key = ""
        openai_api_key = ""

    monkeypatch.setattr("gads_analytics.ask.get_settings", lambda: _Settings())
    payload = answer_strategy(session, account, "What should the strategy be?", date(2026, 9, 2), date(2026, 9, 15))

    assert payload["council"] is None
    assert payload["model"] == "deterministic"
    assert "not each day against the day before" in payload["answer"]
    assert payload["start_date"] == "2026-09-02"
    assert payload["end_date"] == "2026-09-15"
    assert payload["llm_error"] is None


def test_strategy_says_when_the_council_is_out_of_requests(session, monkeypatch):
    seeded = seed_report_account(session, date(2026, 9, 15))
    account = session.get(AdAccount, seeded["account_id"])

    class _Settings:
        openrouter_api_key = "present"
        openai_api_key = ""
        openai_model = "gpt-4.1-mini"

    def _limited(*_args, **_kwargs):
        raise CouncilRateLimited()

    monkeypatch.setattr("gads_analytics.ask.get_settings", lambda: _Settings())
    monkeypatch.setattr("gads_analytics.ask.run_council", _limited)
    payload = answer_strategy(session, account, "What should the strategy be?", date(2026, 9, 2), date(2026, 9, 15))

    assert payload["llm_error"] == "rate_limit"
    assert payload["model"] == "deterministic"
    assert "out of requests" in payload["answer"]
    assert "not each day against the day before" in payload["answer"]


def test_strategy_uses_the_backup_key_when_the_first_is_out_of_requests(session, monkeypatch):
    seeded = seed_report_account(session, date(2026, 9, 15))
    account = session.get(AdAccount, seeded["account_id"])

    class _Settings:
        openrouter_api_key = "primary"
        openrouter_backup_api_key = "backup"
        openai_api_key = ""
        openai_model = "gpt-4.1-mini"

    def _run(_question, _report, api_key=None):
        if api_key == "primary":
            raise CouncilRateLimited()
        return {"answer": "Backup overview", "council": {"chairman": "backup", "opinions": [], "rankings": []}}

    monkeypatch.setattr("gads_analytics.ask.get_settings", lambda: _Settings())
    monkeypatch.setattr("gads_analytics.ask.run_council", _run)
    payload = answer_strategy(session, account, "What should the strategy be?", date(2026, 9, 2), date(2026, 9, 15))

    assert payload["llm_error"] is None
    assert payload["model"] == "llm-council"
    assert payload["answer"] == "Backup overview"
    assert payload["council"]["chairman"] == "backup"


def test_strategy_uses_a_paid_model_when_free_council_models_are_capped(session, monkeypatch):
    seeded = seed_report_account(session, date(2026, 9, 15))
    account = session.get(AdAccount, seeded["account_id"])

    class _Settings:
        openrouter_api_key = "primary"
        openrouter_backup_api_key = "backup"
        openai_api_key = ""
        openai_model = "gpt-4.1-mini"

    def _limited(*_args, **_kwargs):
        raise CouncilRateLimited()

    monkeypatch.setattr("gads_analytics.ask.get_settings", lambda: _Settings())
    monkeypatch.setattr("gads_analytics.ask.run_council", _limited)
    monkeypatch.setattr("gads_analytics.ask.complete_one", lambda *_args, **_kwargs: "Paid overview")
    payload = answer_strategy(session, account, "What should the strategy be?", date(2026, 9, 2), date(2026, 9, 15))

    assert payload["llm_error"] is None
    assert payload["model"] == "openai/gpt-4.1-mini"
    assert payload["answer"] == "Paid overview"


def test_saved_trends_stay_separate_and_keep_a_rename(session):
    seeded = seed_report_account(session, date(2026, 9, 15))
    account_id = seeded["account_id"]
    first = save_trend_summary(session, account_id, date(2026, 9, 2), date(2026, 9, 15), "What is the strategy?", "Spend rose.")
    again = save_trend_summary(session, account_id, date(2026, 9, 2), date(2026, 9, 15), "What is the strategy?", "Spend rose further.")
    other = save_trend_summary(session, account_id, date(2026, 8, 1), date(2026, 8, 31), "What is the strategy?", "August was flat.")

    assert first == again
    assert other != first
    assert rename_saved_report(session, account_id, first, "Quarter check")["title"] == "Quarter check"
    rows = [row for row in list_saved_reports(session, account_id) if row["kind"].startswith("trend:")]
    assert len(rows) == 2
    kept = next(row for row in rows if row["id"] == first)
    assert kept["title"] == "Quarter check"
    assert kept["body"] == "Spend rose further."
    assert kept["period_start"] == "2026-09-02"

    payload, filename = trend_notes_zip(session, account_id, date(2026, 9, 1), date(2026, 9, 30))
    assert filename == "2026-09-01-to-2026-09-30-trends.zip"
    archive = zipfile.ZipFile(io.BytesIO(payload))
    assert archive.namelist() == ["2026-09-02-quarter-check-full.txt"]
    assert archive.read("2026-09-02-quarter-check-full.txt") == b"Spend rose further."
