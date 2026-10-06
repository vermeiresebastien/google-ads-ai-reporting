from datetime import date, timedelta

from gads_ingestion.jobs import (
    _set_step_status,
    begin_sync_progress,
    plan_sync_steps,
    sync_progress,
)


def test_history_plan_counts_every_slice():
    end = date(2026, 10, 5)
    start = end - timedelta(days=394)
    steps = plan_sync_steps(start, end)
    assert len(steps) == 30
    assert steps[0]["dataset"] == "campaigns"
    assert steps[-1]["dataset"] == "change_events"
    assert sum(step["dataset"] == "search_terms" for step in steps) == 5


def test_progress_advances_and_stops_on_failure():
    steps = plan_sync_steps(date(2026, 10, 1), date(2026, 10, 5))
    begin_sync_progress("account-1", steps)
    assert sync_progress("account-1")["percent"] == 0
    _set_step_status("account-1", 0, "running")
    _set_step_status("account-1", 0, "completed")
    advanced = sync_progress("account-1")
    assert advanced["completed"] == 1
    assert advanced["status"] == "running"
    _set_step_status("account-1", 1, "failed", error="Google refused the customer")
    failed = sync_progress("account-1")
    assert failed["status"] == "failed"
    assert failed["completed"] == 1
    assert "Google refused" in failed["error"]
