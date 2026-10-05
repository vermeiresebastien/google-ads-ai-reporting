from __future__ import annotations

from gads_ingestion.google_ads.queries import customer_clients_query, customer_query
from gads_ingestion.mapping import text_id


def discover_accounts(client) -> list[dict]:
    found: dict[str, dict] = {}
    for resource in client.list_accessible_customers():
        customer_id = resource.split("/")[-1]
        rows = client.search(customer_id, customer_query())
        if not rows:
            continue
        customer = rows[0].get("customer") or {}
        if customer.get("manager"):
            children = client.search(customer_id, customer_clients_query())
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
    return list(found.values())
