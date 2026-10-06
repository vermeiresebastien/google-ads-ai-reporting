from __future__ import annotations

from gads.models import ProposedAction


MATCH_TYPES = {
    "EXACT": "EXACT",
    "PHRASE": "PHRASE",
    "BROAD": "BROAD",
}


class GoogleMutationError(RuntimeError):
    """Raised when a Google Ads mutate call fails."""


def apply_google_action(client, customer_id: str, action: ProposedAction, *, dry_run: bool = False) -> dict:
    if action.action_type == "add_negative_keyword":
        return add_campaign_negative_keyword(client, customer_id, action.params or {}, validate_only=dry_run)
    if action.action_type == "increase_budget":
        return update_campaign_daily_budget(client, customer_id, action.params or {}, validate_only=dry_run)
    raise GoogleMutationError(f"Unsupported action type: {action.action_type}")


def add_campaign_negative_keyword(
    client,
    customer_id: str,
    params: dict,
    *,
    validate_only: bool = False,
) -> dict:
    text = str(params.get("keyword_text") or "").strip()
    google_campaign_id = str(params.get("google_campaign_id") or "").strip()
    match_type = MATCH_TYPES.get(str(params.get("match_type") or "PHRASE").upper(), "PHRASE")
    if not text or not google_campaign_id:
        raise GoogleMutationError("Negative keyword actions require keyword_text and google_campaign_id")

    if hasattr(client, "add_campaign_negative_keyword"):
        return client.add_campaign_negative_keyword(
            customer_id,
            google_campaign_id,
            text,
            match_type,
            validate_only=validate_only,
        )

    from google.ads.googleads.errors import GoogleAdsException

    cid = customer_id.replace("-", "")
    service = client._client.get_service("CampaignCriterionService")
    operation = client._client.get_type("CampaignCriterionOperation")
    criterion = operation.create
    criterion.campaign = f"customers/{cid}/campaigns/{google_campaign_id}"
    criterion.negative = True
    criterion.keyword.text = text
    criterion.keyword.match_type = client._client.enums.KeywordMatchTypeEnum[match_type]

    request = client._client.get_type("MutateCampaignCriteriaRequest")
    request.customer_id = cid
    request.operations = [operation]
    request.validate_only = validate_only
    try:
        response = service.mutate_campaign_criteria(request=request)
    except GoogleAdsException as exc:
        raise GoogleMutationError(_google_error_message(exc)) from exc

    results = []
    for result in getattr(response, "results", []) or []:
        results.append({"resource_name": getattr(result, "resource_name", "")})
    return {
        "operation": "add_campaign_negative_keyword",
        "validate_only": validate_only,
        "keyword_text": text,
        "match_type": match_type,
        "google_campaign_id": google_campaign_id,
        "results": results,
    }


def update_campaign_daily_budget(
    client,
    customer_id: str,
    params: dict,
    *,
    validate_only: bool = False,
) -> dict:
    google_campaign_id = str(params.get("google_campaign_id") or "").strip()
    proposed = params.get("proposed_daily_budget")
    if not google_campaign_id or proposed is None:
        raise GoogleMutationError("Budget actions require google_campaign_id and proposed_daily_budget")

    amount_micros = int(round(float(proposed) * 1_000_000))
    if amount_micros <= 0:
        raise GoogleMutationError("Proposed daily budget must be positive")

    if hasattr(client, "update_campaign_daily_budget"):
        return client.update_campaign_daily_budget(
            customer_id,
            google_campaign_id,
            amount_micros,
            validate_only=validate_only,
        )

    from google.ads.googleads.errors import GoogleAdsException
    from google.protobuf import field_mask_pb2

    cid = customer_id.replace("-", "")
    budget_resource = _campaign_budget_resource(client, cid, google_campaign_id)
    service = client._client.get_service("CampaignBudgetService")
    operation = client._client.get_type("CampaignBudgetOperation")
    budget = operation.update
    budget.resource_name = budget_resource
    budget.amount_micros = amount_micros
    operation.update_mask.CopyFrom(field_mask_pb2.FieldMask(paths=["amount_micros"]))

    request = client._client.get_type("MutateCampaignBudgetsRequest")
    request.customer_id = cid
    request.operations = [operation]
    request.validate_only = validate_only
    try:
        response = service.mutate_campaign_budgets(request=request)
    except GoogleAdsException as exc:
        raise GoogleMutationError(_google_error_message(exc)) from exc

    results = []
    for result in getattr(response, "results", []) or []:
        results.append({"resource_name": getattr(result, "resource_name", "")})
    return {
        "operation": "update_campaign_daily_budget",
        "validate_only": validate_only,
        "google_campaign_id": google_campaign_id,
        "amount_micros": amount_micros,
        "proposed_daily_budget": float(proposed),
        "budget_resource_name": budget_resource,
        "results": results,
    }


def _campaign_budget_resource(client, customer_id: str, google_campaign_id: str) -> str:
    query = (
        "SELECT campaign.id, campaign_budget.resource_name, campaign_budget.amount_micros "
        f"FROM campaign WHERE campaign.id = {int(google_campaign_id)}"
    )
    rows = client.search(customer_id, query)
    if not rows:
        raise GoogleMutationError(f"Campaign {google_campaign_id} was not found in Google Ads")
    budget = rows[0].get("campaign_budget") or {}
    resource = budget.get("resource_name")
    if not resource:
        raise GoogleMutationError(f"No campaign budget found for campaign {google_campaign_id}")
    return resource


def _google_error_message(exc) -> str:
    parts = [str(exc)]
    failure = getattr(exc, "failure", None)
    errors = getattr(failure, "errors", None) if failure is not None else None
    if errors:
        for error in errors:
            message = getattr(error, "message", None)
            if message:
                parts.append(str(message))
    return "; ".join(parts)[:2000]
