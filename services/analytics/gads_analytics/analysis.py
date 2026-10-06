from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from gads_analytics.metrics import Totals, compare_metric_sets, ratio


@dataclass
class Thresholds:
    min_spend_for_waste: float = 50
    spend_anomaly_pct: float = 0.30
    cpa_anomaly_pct: float = 0.25
    roas_anomaly_pct: float = 0.20
    conversion_anomaly_pct: float = 0.25
    cpc_anomaly_pct: float = 0.25
    cvr_anomaly_pct: float = 0.20
    zero_conversion_min_spend: float = 25
    budget_lost_is_min: float = 0.15
    min_clicks: int = 10
    min_spend_for_anomaly: float = 20


def _num(value, default: float) -> float:
    if value is None:
        return default
    return float(value)


def thresholds_from_settings(row) -> Thresholds:
    if row is None:
        return Thresholds()
    return Thresholds(
        min_spend_for_waste=_num(row.min_spend_for_waste, 50),
        spend_anomaly_pct=_num(row.spend_anomaly_pct, 0.30),
        cpa_anomaly_pct=_num(row.cpa_anomaly_pct, 0.25),
        roas_anomaly_pct=_num(row.roas_anomaly_pct, 0.20),
        conversion_anomaly_pct=_num(row.conversion_anomaly_pct, 0.25),
        cpc_anomaly_pct=_num(row.cpc_anomaly_pct, 0.25),
        cvr_anomaly_pct=_num(row.cvr_anomaly_pct, 0.20),
        zero_conversion_min_spend=_num(row.zero_conversion_min_spend, 25),
        budget_lost_is_min=_num(row.budget_lost_is_min, 0.15),
        min_clicks=int(row.min_clicks or 10),
        min_spend_for_anomaly=_num(row.min_spend_for_anomaly, 20),
    )


def compare_totals(current: Totals, baseline: Totals) -> dict:
    return {
        "current": current.as_dict(),
        "baseline": baseline.as_dict(),
        "changes": compare_metric_sets(current.as_dict(), baseline.as_dict()),
    }


def campaign_drivers(
    current: dict[str, Totals],
    previous: dict[str, Totals],
    names: dict[str, str],
    limit: int = 5,
) -> dict:
    ids = set(current) | set(previous)
    previous_cost = sum(previous.get(item, Totals()).cost for item in ids)
    previous_conversions = sum(previous.get(item, Totals()).conversions for item in ids)
    account_prev_cpa = ratio(previous_cost, previous_conversions) or 0.0
    rows = []
    for campaign_id in ids:
        now = current.get(campaign_id, Totals())
        before = previous.get(campaign_id, Totals())
        spend_delta = now.cost - before.cost
        conversion_delta = now.conversions - before.conversions
        value_delta = now.conversion_value - before.conversion_value
        rows.append(
            {
                "campaign_id": campaign_id,
                "name": names.get(campaign_id, campaign_id),
                "spend_delta": spend_delta,
                "conversion_delta": conversion_delta,
                "value_delta": value_delta,
                "cpa_pressure": spend_delta - account_prev_cpa * conversion_delta,
                "current": now.as_dict(),
                "previous": before.as_dict(),
            }
        )
    return {
        "increased_spend": sorted(rows, key=lambda row: row["spend_delta"], reverse=True)[:limit],
        "lost_conversions": sorted(rows, key=lambda row: row["conversion_delta"])[:limit],
        "increased_cpa": sorted(rows, key=lambda row: row["cpa_pressure"], reverse=True)[:limit],
        "reduced_conversion_value": sorted(rows, key=lambda row: row["value_delta"])[:limit],
    }


def _finding(kind: str, metric: str, current: float | None, baseline: float | None, evidence: list[str]) -> dict:
    percent = None
    if current is not None and baseline not in (None, 0):
        percent = (current - baseline) / abs(baseline)
    return {
        "type": kind,
        "metric": metric,
        "current": current,
        "baseline": baseline,
        "percent_change": percent,
        "evidence": evidence,
        "confidence": "high",
    }


def detect_anomalies(current: Totals, baseline: Totals, thresholds: Thresholds) -> list[dict]:
    if max(current.cost, baseline.cost) < thresholds.min_spend_for_anomaly:
        return []
    current_metrics = current.as_dict()
    baseline_metrics = baseline.as_dict()
    findings = []

    spend_pct = _pct(current.cost, baseline.cost)
    if spend_pct is not None and spend_pct >= thresholds.spend_anomaly_pct:
        findings.append(
            _finding(
                "spend_anomaly",
                "cost",
                current.cost,
                baseline.cost,
                [f"Spend moved from {baseline.cost:.2f} to {current.cost:.2f} ({spend_pct:.1%})"],
            )
        )

    if current.conversions == 0 and current.cost >= thresholds.zero_conversion_min_spend:
        findings.append(
            _finding(
                "zero_conversion_spend",
                "conversions",
                0,
                baseline.conversions,
                [f"Spend was {current.cost:.2f} with zero conversions"],
            )
        )

    cpa_pct = _pct(current_metrics["cost_per_conversion"], baseline_metrics["cost_per_conversion"])
    if cpa_pct is not None and cpa_pct >= thresholds.cpa_anomaly_pct:
        findings.append(
            _finding(
                "cpa_anomaly",
                "cost_per_conversion",
                current_metrics["cost_per_conversion"],
                baseline_metrics["cost_per_conversion"],
                [
                    f"CPA moved from {baseline_metrics['cost_per_conversion']:.2f} to {current_metrics['cost_per_conversion']:.2f} ({cpa_pct:.1%})"
                ],
            )
        )

    roas_pct = _pct(current_metrics["roas"], baseline_metrics["roas"])
    if roas_pct is not None and roas_pct <= -thresholds.roas_anomaly_pct:
        findings.append(
            _finding(
                "roas_anomaly",
                "roas",
                current_metrics["roas"],
                baseline_metrics["roas"],
                [f"ROAS moved from {baseline_metrics['roas']:.2f} to {current_metrics['roas']:.2f} ({roas_pct:.1%})"],
            )
        )

    conv_pct = _pct(current.conversions, baseline.conversions)
    if conv_pct is not None and conv_pct <= -thresholds.conversion_anomaly_pct:
        findings.append(
            _finding(
                "conversion_anomaly",
                "conversions",
                current.conversions,
                baseline.conversions,
                [f"Conversions moved from {baseline.conversions:.2f} to {current.conversions:.2f} ({conv_pct:.1%})"],
            )
        )

    cpc_pct = _pct(current_metrics["average_cpc"], baseline_metrics["average_cpc"])
    if cpc_pct is not None and cpc_pct >= thresholds.cpc_anomaly_pct:
        findings.append(
            _finding(
                "cpc_anomaly",
                "average_cpc",
                current_metrics["average_cpc"],
                baseline_metrics["average_cpc"],
                [
                    f"CPC moved from {baseline_metrics['average_cpc']:.2f} to {current_metrics['average_cpc']:.2f} ({cpc_pct:.1%})"
                ],
            )
        )

    cvr_pct = _pct(current_metrics["conversion_rate"], baseline_metrics["conversion_rate"])
    if cvr_pct is not None and abs(cvr_pct) >= thresholds.cvr_anomaly_pct:
        findings.append(
            _finding(
                "conversion_rate_anomaly",
                "conversion_rate",
                current_metrics["conversion_rate"],
                baseline_metrics["conversion_rate"],
                [f"Conversion rate changed by {cvr_pct:.1%}"],
            )
        )
    return findings


def _pct(current: float | None, baseline: float | None) -> float | None:
    if current is None or baseline is None or baseline == 0:
        return None
    return (current - baseline) / abs(baseline)


def wasted_spend_candidates(rows: list[dict], thresholds: Thresholds, account_cpa: float | None) -> list[dict]:
    candidates = []
    for row in rows:
        totals: Totals = row["totals"]
        if totals.cost < thresholds.min_spend_for_waste or totals.clicks < thresholds.min_clicks:
            continue
        reasons = []
        if totals.conversions == 0 and totals.cost >= thresholds.zero_conversion_min_spend:
            reasons.append(f"Spend {totals.cost:.2f} produced zero conversions across {int(totals.clicks)} clicks")
        elif account_cpa and totals.conversions > 0:
            cpa = totals.cost / totals.conversions
            if cpa > account_cpa * (1 + thresholds.cpa_anomaly_pct):
                reasons.append(f"CPA {cpa:.2f} is above the account CPA of {account_cpa:.2f}")
        if not reasons:
            continue
        candidates.append(
            {
                "kind": row["kind"],
                "id": row.get("id"),
                "name": row["name"],
                "campaign_id": row.get("campaign_id"),
                "campaign_name": row.get("campaign_name"),
                "reasons": reasons,
                "metrics": totals.as_dict(),
                "label": "candidate",
            }
        )
    return sorted(candidates, key=lambda item: item["metrics"]["cost"], reverse=True)


def budget_opportunities(campaigns: list[dict], thresholds: Thresholds, account: Totals) -> list[dict]:
    account_cpa = ratio(account.cost, account.conversions)
    account_roas = ratio(account.conversion_value, account.cost)
    opportunities = []
    for campaign in campaigns:
        lost = campaign.get("budget_lost_impression_share")
        totals: Totals = campaign["totals"]
        if lost is None or lost < thresholds.budget_lost_is_min:
            continue
        if totals.cost < thresholds.min_spend_for_anomaly or totals.conversions <= 0:
            continue
        evidence = [f"Budget lost impression share was {lost:.1%}"]
        cpa = totals.cost / totals.conversions
        roas = ratio(totals.conversion_value, totals.cost)
        performance_ok = False
        if account_cpa is not None and cpa <= account_cpa * 1.1:
            performance_ok = True
            evidence.append(f"CPA {cpa:.2f} is within 10% of the account CPA {account_cpa:.2f}")
        if account_roas is not None and roas is not None and roas >= account_roas * 0.9:
            performance_ok = True
            evidence.append(f"ROAS {roas:.2f} is within 10% of the account ROAS {account_roas:.2f}")
        if not performance_ok:
            continue
        opportunities.append(
            {
                "campaign_id": campaign["campaign_id"],
                "name": campaign["name"],
                "budget_lost_impression_share": lost,
                "metrics": totals.as_dict(),
                "evidence": evidence,
                "confidence": "high" if len(evidence) >= 2 else "medium",
            }
        )
    return sorted(opportunities, key=lambda item: item["budget_lost_impression_share"], reverse=True)


def top_changes(drivers: dict, limit: int = 5) -> list[dict]:
    seen = set()
    changes = []
    for bucket in ("increased_cpa", "lost_conversions", "increased_spend", "reduced_conversion_value"):
        for row in drivers.get(bucket, []):
            if row["campaign_id"] in seen:
                continue
            if abs(row["spend_delta"]) < 0.01 and abs(row["conversion_delta"]) < 0.01 and abs(row["value_delta"]) < 0.01:
                continue
            seen.add(row["campaign_id"])
            changes.append(
                {
                    "campaign_id": row["campaign_id"],
                    "name": row["name"],
                    "bucket": bucket,
                    "spend_delta": row["spend_delta"],
                    "conversion_delta": row["conversion_delta"],
                    "value_delta": row["value_delta"],
                    "current": row["current"],
                    "previous": row["previous"],
                }
            )
            if len(changes) >= limit:
                return changes
    return changes


def recommendations(anomalies: list[dict], waste: list[dict], budgets: list[dict], changes: list[dict]) -> list[dict]:
    actions = []
    for item in waste[:2]:
        metrics = item["metrics"]
        actions.append(
            {
                "action": (
                    f"Add “{item['name']}” as a negative keyword. "
                    f"It spent {metrics['cost']:.2f} across {int(metrics['clicks'])} clicks "
                    f"and produced {metrics['conversions']:.2f} conversions."
                ),
                "evidence": item["reasons"],
                "confidence": "medium",
            }
        )
    for item in budgets:
        if len(actions) >= 3:
            break
        lost = item["budget_lost_impression_share"]
        metrics = item["metrics"]
        cpa = metrics.get("cost_per_conversion")
        cpa_text = f" CPA is {cpa:.2f}." if cpa else ""
        actions.append(
            {
                "action": (
                    f"Move budget toward {item['name']}. "
                    f"The budget is hiding {lost:.0%} of eligible impressions while efficiency stays near the account.{cpa_text}"
                ),
                "evidence": item["evidence"],
                "confidence": item["confidence"],
            }
        )
    if len(actions) < 3 and anomalies:
        evidence = anomalies[0]["evidence"]
        actions.append(
            {
                "action": f"Check the campaigns behind the account move before editing bids. {evidence[0]}",
                "evidence": evidence,
                "confidence": "medium",
            }
        )
    if changes and not actions:
        actions.append(
            {
                "action": "Leave bids and budgets as they are. The compared change is inside the configured thresholds.",
                "evidence": ["Configured anomaly thresholds were not crossed"],
                "confidence": "low",
            }
        )
    if not actions:
        actions.append(
            {
                "action": "Leave the account as it is. Spend, efficiency, and query waste are inside the configured thresholds.",
                "evidence": ["No anomaly, waste candidate, or budget opportunity met the configured thresholds"],
                "confidence": "high",
            }
        )
    return actions[:3]


def evidence_claims(comparison: dict, drivers: dict) -> list[dict]:
    claims = []
    changes = comparison["changes"]
    parts = []
    for metric, label in (
        ("cost", "Spend"),
        ("conversions", "Conversions"),
        ("cost_per_conversion", "CPA"),
        ("roas", "ROAS"),
    ):
        percent = changes[metric]["percent"]
        if percent is None:
            continue
        parts.append(f"{label} changed {percent:.1%}")
    if parts:
        driver = next((row for row in drivers.get("increased_cpa", []) if abs(row["cpa_pressure"]) > 0), None)
        evidence = list(parts)
        if driver:
            evidence.append(
                f"{driver['name']} spend delta {driver['spend_delta']:.2f}, conversion delta {driver['conversion_delta']:.2f}"
            )
        claims.append(
            {
                "claim": "Account performance moved relative to the comparison baseline.",
                "evidence": evidence,
                "confidence": "high" if len(evidence) >= 2 else "medium",
            }
        )
    return claims


def empty_freshness(last_sync) -> dict:
    return {"last_successful_sync": _iso(last_sync), "datasets": {}}


def _iso(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, date):
        return value.isoformat()
    return value.isoformat()
