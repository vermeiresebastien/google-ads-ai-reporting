from __future__ import annotations

from gads.config import get_settings
from gads.models import AdAccount
from gads.security import decrypt_secret


class GoogleAdsApiClient:
    """Official client wrapper. Isolated so an API version bump stays in this module."""

    def __init__(self, refresh_token: str, login_customer_id: str | None = None):
        settings = get_settings()
        from google.ads.googleads.client import GoogleAdsClient

        config = {
            "developer_token": settings.google_ads_developer_token,
            "client_id": settings.google_ads_client_id,
            "client_secret": settings.google_ads_client_secret,
            "refresh_token": refresh_token,
            "use_proto_plus": True,
        }
        if login_customer_id:
            config["login_customer_id"] = login_customer_id.replace("-", "")
        self._client = GoogleAdsClient.load_from_dict(config, version=settings.google_ads_api_version)

    def search(self, customer_id: str, query: str) -> list[dict]:
        from google.protobuf.json_format import MessageToDict

        service = self._client.get_service("GoogleAdsService")
        rows: list[dict] = []
        stream = service.search_stream(customer_id=customer_id.replace("-", ""), query=query)
        for batch in stream:
            for row in batch.results:
                rows.append(MessageToDict(row._pb, preserving_proto_field_name=True))
        return rows

    def list_accessible_customers(self) -> list[str]:
        service = self._client.get_service("CustomerService")
        response = service.list_accessible_customers()
        return list(response.resource_names)


def build_client(account: AdAccount):
    settings = get_settings()
    refresh_token = decrypt_secret(account.connection.refresh_token_encrypted)
    login_customer_id = account.manager_customer_id or settings.google_ads_login_customer_id or None
    return GoogleAdsApiClient(refresh_token=refresh_token, login_customer_id=login_customer_id)


def build_client_for_refresh_token(refresh_token: str, login_customer_id: str | None = None):
    return GoogleAdsApiClient(refresh_token=refresh_token, login_customer_id=login_customer_id)
