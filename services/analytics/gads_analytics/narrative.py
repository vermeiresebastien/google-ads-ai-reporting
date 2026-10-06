from __future__ import annotations

from pathlib import Path


def load_system_prompt() -> str:
    candidates = [
        Path.cwd() / "prompts" / "analyst.md",
        Path(__file__).resolve().parents[3] / "prompts" / "analyst.md",
    ]
    for path in candidates:
        if path.exists():
            return path.read_text(encoding="utf-8")
    return "You are a performance marketing analyst. Use only the supplied data."


def _money(value) -> str:
    if value is None:
        return "n/a"
    return f"{float(value):.2f}"


def _pct(value) -> str:
    if value is None:
        return "n/a"
    return f"{float(value):.1%}"


def _num(value) -> str:
    if value is None:
        return "n/a"
    number = float(value)
    if number.is_integer():
        return str(int(number))
    return f"{number:.2f}"


def render_day_change(report: dict) -> str:
    comparison = report.get("comparison") or {}
    current = comparison.get("current") or report.get("account") or {}
    baseline = comparison.get("baseline") or {}
    changes = comparison.get("changes") or {}
    period = comparison.get("period") or {}
    yesterday = period.get("baseline_start")
    today = period.get("current_end")
    lines = [f"Change from {yesterday} to {today}", ""]
    for metric, label in (
        ("cost", "Spend"),
        ("conversions", "Conversions"),
        ("conversion_value", "Conversion value"),
        ("cost_per_conversion", "CPA"),
        ("roas", "ROAS"),
        ("average_cpc", "CPC"),
        ("conversion_rate", "Conversion rate"),
    ):
        change = changes.get(metric) or {}
        lines.append(
            f"- {label}: {yesterday} {_num(baseline.get(metric))}, {today} {_num(current.get(metric))}, "
            f"change {_pct(change.get('percent'))}."
        )
    lines.append("")
    lines.append("Campaigns that moved")
    top_changes = report.get("top_changes") or []
    if not top_changes:
        lines.append("No campaign moved enough to list.")
    for change in top_changes:
        lines.append(
            f"- {change['name']}: spend delta {_money(change['spend_delta'])}, "
            f"conversion delta {_num(change['conversion_delta'])}."
        )
    return "\n".join(lines)


def render_report(report: dict) -> str:
    account = report.get("account") or {}
    comparison = report.get("comparison") or {}
    current = comparison.get("current") or account
    baseline = comparison.get("baseline") or {}
    changes = comparison.get("changes") or {}
    period = comparison.get("period") or {}
    lines = ["## Executive summary"]
    freshness = report.get("data_freshness") or {}
    if not freshness.get("last_successful_sync"):
        lines.append("Data freshness: no successful sync is recorded, so this report may be empty or stale.")
    else:
        lines.append(f"Data freshness: last successful sync {freshness['last_successful_sync']}.")
    lines.append(
        f"On {report.get('date')}, spend was {_money(account.get('cost'))}, "
        f"conversions were {_num(account.get('conversions'))}, "
        f"conversion value was {_money(account.get('conversion_value'))}, "
        f"CPA was {_money(account.get('cost_per_conversion'))}, "
        f"and ROAS was {_num(account.get('roas'))}."
    )
    lines.append("")
    lines.append("## Performance")
    lines.append(
        f"Comparison: {period.get('current_start')} to {period.get('current_end')} versus "
        f"{period.get('baseline_start')} to {period.get('baseline_end')} ({period.get('normalization', 'totals')})."
    )
    for metric, label in (
        ("cost", "Spend"),
        ("conversions", "Conversions"),
        ("conversion_value", "Conversion value"),
        ("cost_per_conversion", "CPA"),
        ("roas", "ROAS"),
        ("average_cpc", "CPC"),
        ("conversion_rate", "Conversion rate"),
    ):
        change = changes.get(metric) or {}
        lines.append(
            f"- {label}: current {_num(current.get(metric))}, baseline {_num(baseline.get(metric))}, "
            f"change {_pct(change.get('percent'))}."
        )
    lines.append("")
    lines.append("## What changed")
    evidence_claims = report.get("evidence") or []
    if evidence_claims:
        for claim in evidence_claims:
            confidence = claim.get("confidence")
            suffix = f" ({confidence} confidence)" if confidence else ""
            lines.append(f"- Claim{suffix}: {claim.get('claim')}")
            for item in claim.get("evidence") or []:
                lines.append(f"  - Evidence: {item}")
    top_changes = report.get("top_changes") or []
    if not top_changes and not evidence_claims:
        lines.append("No campaign moved enough to list.")
    for change in top_changes:
        lines.append(
            f"- {change['name']}: spend delta {_money(change['spend_delta'])}, "
            f"conversion delta {_num(change['conversion_delta'])}, "
            f"conversion value delta {_money(change['value_delta'])}."
        )
    lines.append("")
    lines.append("## Why it changed")
    drivers = report.get("campaign_drivers") or {}
    why_lines = _why_driver_lines(drivers)
    if not why_lines:
        lines.append("No campaign-level driver is large enough to single out.")
    else:
        lines.extend(why_lines)
        lines.append(
            "Hypothesis: the metric movements above are observations from the comparison. "
            "This report does not prove the underlying cause."
        )
    lines.append("")
    lines.append("## Problems")
    anomalies = report.get("anomalies") or []
    waste = report.get("wasted_spend") or []
    if not anomalies and not waste:
        lines.append("No anomaly or waste candidate crossed the configured thresholds.")
    for anomaly in anomalies:
        confidence = anomaly.get("confidence")
        suffix = f" ({confidence} confidence)" if confidence else ""
        lines.append(f"- Anomaly {anomaly['type']}{suffix}: {'; '.join(anomaly.get('evidence') or [])}.")
    for item in waste:
        lines.append(f"- Waste candidate {item['name']}: {'; '.join(item.get('reasons') or [])}.")
    lines.append("")
    lines.append("## Opportunities")
    opportunities = report.get("budget_opportunities") or []
    if not opportunities:
        lines.append("No budget opportunity has both a material budget constraint and acceptable efficiency.")
    for item in opportunities:
        confidence = item.get("confidence")
        suffix = f" ({confidence} confidence)" if confidence else ""
        lines.append(f"- {item['name']}{suffix}: {'; '.join(item.get('evidence') or [])}.")
    lines.append("")
    lines.append("## Recommended actions")
    for action in report.get("recommended_actions") or []:
        confidence = action.get("confidence")
        suffix = f" ({confidence} confidence)" if confidence else ""
        lines.append(
            f"- {action['action']}{suffix} Evidence: {'; '.join(action.get('evidence') or [])}."
        )
    recent = report.get("recent_changes") or []
    if recent:
        lines.append("")
        lines.append("Recent account changes:")
        for change in recent[:8]:
            lines.append(
                f"- {change.get('event_timestamp')}: {change.get('resource_type')} {change.get('change_type')} "
                f"on {change.get('field_changed') or change.get('resource_changed_name')} "
                f"by {change.get('user_email') or 'unknown user'} via {change.get('client_type') or 'unknown client'}."
            )
    return "\n".join(lines)


_DRIVER_LABELS = (
    ("increased_cpa", "CPA-pressure"),
    ("lost_conversions", "lost-conversions"),
    ("increased_spend", "increased-spend"),
    ("reduced_conversion_value", "reduced-conversion-value"),
)


def _why_driver_lines(drivers: dict) -> list[str]:
    lines: list[str] = []
    seen: set[str] = set()
    for bucket, label in _DRIVER_LABELS:
        for row in (drivers.get(bucket) or [])[:2]:
            campaign_id = str(row.get("campaign_id") or row.get("name") or "")
            if campaign_id in seen:
                continue
            seen.add(campaign_id)
            current_row = row.get("current") or {}
            previous_row = row.get("previous") or {}
            lines.append(
                f"- {row['name']} is a main {label} campaign. "
                f"Spend delta {_money(row.get('spend_delta'))}, "
                f"conversion delta {_num(row.get('conversion_delta'))}, "
                f"conversion value delta {_money(row.get('value_delta'))}. "
                f"CPC moved from {_num(previous_row.get('average_cpc'))} to {_num(current_row.get('average_cpc'))} "
                f"and conversion rate moved from {_num(previous_row.get('conversion_rate'))} "
                f"to {_num(current_row.get('conversion_rate'))}."
            )
            if len(lines) >= 4:
                return lines
    return lines


def tools_for_question(question: str) -> set[str]:
    text = question.lower()
    tools = {"summary", "freshness"}
    if any(word in text for word in ("yesterday", "today", "daily", "report", "what happened", "what should")):
        tools.add("daily_report")
    if any(word in text for word in ("week", "compare", "versus", " vs ")):
        tools.add("compare")
    if any(word in text for word in ("why", "driver", "campaign", "roas", "cpa", "fall", "drop")):
        tools.update({"drivers", "campaigns", "anomalies"})
    if any(word in text for word in ("waste", "search term", "negative", "keyword")):
        tools.update({"search_waste", "search_terms", "keywords"})
    if "budget" in text or "opportunity" in text:
        tools.add("budget")
    if "change" in text:
        tools.add("changes")
    if "anomal" in text:
        tools.add("anomalies")
    if tools <= {"summary", "freshness"}:
        tools.add("daily_report")
    return tools
