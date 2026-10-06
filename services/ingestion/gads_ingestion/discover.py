from __future__ import annotations

from gads_ingestion.google_ads.queries import customer_clients_query, customer_query
from gads_ingestion.mapping import text_id


class DiscoveryError(Exception):
    pass


def discover_accounts(client) -> list[dict]:
    found: dict[str, dict] = {}
    failures: list[str] = []
    try:
        resources = client.list_accessible_customers()
    except Exception as exc:
        raise DiscoveryError(str(exc)) from exc
    for resource in resources:
        customer_id = resource.split("/")[-1]
        try:
            rows = client.search(customer_id, customer_query())
        except Exception as exc:
            failures.append(str(exc))
            continue
        if not rows:
            continue
        customer = rows[0].get("customer") or {}
        if customer.get("manager"):
            try:
                children = client.search(customer_id, customer_clients_query())
            except Exception as exc:
                failures.append(str(exc))
                continue
            for child_row in children:
                child = child_row.get("customer_client") or {}
                if child.get("manager"):
                    continue
                child_id = text_id(child.get("id")) or (child.get("client_customer") or "").split("/")[-1]
                if not child_id:
                    continue
                found[child_id] = {
                    "customer_id": child_id,
                    "manager_customer_id": customer_id,
                    "account_name": child.get("descriptive_name") or "",
                    "currency_code": child.get("currency_code") or "",
                    "timezone": child.get("time_zone") or "",
                    "status": child.get("status") or "ENABLED",
                }
        else:
            found[customer_id] = {
                "customer_id": customer_id,
                "manager_customer_id": None,
                "account_name": customer.get("descriptive_name") or "",
                "currency_code": customer.get("currency_code") or "",
                "timezone": customer.get("time_zone") or "",
                "status": customer.get("status") or "ENABLED",
            }
    if not found and failures:
        raise DiscoveryError(failures[0])
    return list(found.values())
