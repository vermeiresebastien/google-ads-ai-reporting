from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

import httpx
from gads.config import Settings, get_settings
from gads.models import AccountAnalyticsSettings, AdAccount, PlatformConnection
from gads.platforms import platform_spec
from gads.security import encrypt_secret
from sqlalchemy import select
from sqlalchemy.orm import Session


@dataclass(frozen=True)
class OAuthProvider:
    platform: str
    authorize_url: str
    token_url: str
    scopes: str
    client_id_attr: str
    client_secret_attr: str
    extra_authorize: dict[str, str] | None = None
    extra_token: dict[str, str] | None = None


PROVIDERS: dict[str, OAuthProvider] = {
    "microsoft": OAuthProvider(
        "microsoft",
        "https://login.microsoftonline.com/common/oauth2/v2.0/authorize",
        "https://login.microsoftonline.com/common/oauth2/v2.0/token",
        "https://ads.microsoft.com/msads.manage offline_access openid profile email User.Read",
        "microsoft_ads_client_id",
        "microsoft_ads_client_secret",
    ),
    "meta": OAuthProvider(
        "meta",
        "https://www.facebook.com/v21.0/dialog/oauth",
        "https://graph.facebook.com/v21.0/oauth/access_token",
        "ads_read,business_management,email",
        "meta_app_id",
        "meta_app_secret",
    ),
    "linkedin": OAuthProvider(
        "linkedin",
        "https://www.linkedin.com/oauth/v2/authorization",
        "https://www.linkedin.com/oauth/v2/accessToken",
        "r_ads r_ads_reporting r_organization_social openid profile email",
        "linkedin_client_id",
        "linkedin_client_secret",
    ),
    "x": OAuthProvider(
        "x",
        "https://twitter.com/i/oauth2/authorize",
        "https://api.twitter.com/2/oauth2/token",
        "tweet.read users.read offline.access",
        "x_client_id",
        "x_client_secret",
        extra_authorize={"code_challenge": "challenge", "code_challenge_method": "plain"},
        extra_token={"code_verifier": "challenge"},
    ),
    "reddit": OAuthProvider(
        "reddit",
        "https://www.reddit.com/api/v1/authorize",
        "https://www.reddit.com/api/v1/access_token",
        "adsread identity",
        "reddit_client_id",
        "reddit_client_secret",
        extra_authorize={"duration": "permanent"},
    ),
}


def redirect_uri(settings: Settings, platform: str) -> str:
    return f"{settings.gads_api_base_url.rstrip('/')}/api/platforms/{platform}/oauth/callback"


def authorization_url(platform: str, state: str) -> str:
    provider = PROVIDERS[platform]
    settings = get_settings()
    client_id = getattr(settings, provider.client_id_attr)
    query = {
        "client_id": client_id,
        "redirect_uri": redirect_uri(settings, platform),
        "response_type": "code",
        "scope": provider.scopes,
        "state": state,
    }
    if provider.extra_authorize:
        query.update(provider.extra_authorize)
    if platform == "microsoft":
        query["response_mode"] = "query"
    return f"{provider.authorize_url}?{urlencode(query)}"


def exchange_code(platform: str, code: str) -> dict:
    provider = PROVIDERS[platform]
    settings = get_settings()
    client_id = getattr(settings, provider.client_id_attr)
    client_secret = getattr(settings, provider.client_secret_attr)
    data = {
        "code": code,
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": redirect_uri(settings, platform),
        "grant_type": "authorization_code",
    }
    if provider.extra_token:
        data.update(provider.extra_token)
    headers = {"Accept": "application/json"}
    auth = None
    if platform == "reddit":
        auth = (client_id, client_secret)
        data.pop("client_id", None)
        data.pop("client_secret", None)
        headers["User-Agent"] = "google-ads-ai-reporting/1.0"
    if platform == "linkedin":
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    response = httpx.post(provider.token_url, data=data, headers=headers, auth=auth, timeout=30)
    response.raise_for_status()
    return response.json()


def discover_accounts(platform: str, access_token: str) -> list[dict]:
    if platform == "meta":
        return _discover_meta(access_token)
    if platform == "linkedin":
        return _discover_linkedin(access_token)
    if platform == "microsoft":
        return _discover_microsoft(access_token)
    if platform == "x":
        return _discover_x(access_token)
    if platform == "reddit":
        return _discover_reddit(access_token)
    return []


def _discover_meta(access_token: str) -> list[dict]:
    response = httpx.get(
        "https://graph.facebook.com/v21.0/me/adaccounts",
        params={"fields": "account_id,name,currency,timezone_name,account_status", "limit": 100},
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=30,
    )
    response.raise_for_status()
    rows = []
    for item in response.json().get("data", []):
        status = "ENABLED" if str(item.get("account_status")) in {"1", "ACTIVE", "active"} else "DISABLED"
        rows.append(
            {
                "customer_id": str(item.get("account_id") or item.get("id", "")).removeprefix("act_"),
                "manager_customer_id": None,
                "account_name": item.get("name") or "",
                "currency_code": item.get("currency") or "",
                "timezone": item.get("timezone_name") or "",
                "status": status,
            }
        )
    return rows


def _discover_linkedin(access_token: str) -> list[dict]:
    response = httpx.get(
        "https://api.linkedin.com/rest/adAccounts",
        params={"q": "search", "search": "(status:(values:List(ACTIVE,DRAFT)))", "pageSize": 100},
        headers={
            "Authorization": f"Bearer {access_token}",
            "LinkedIn-Version": "202411",
            "X-Restli-Protocol-Version": "2.0.0",
        },
        timeout=30,
    )
    if response.status_code >= 400:
        profile = httpx.get(
            "https://api.linkedin.com/v2/userinfo",
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=30,
        )
        if profile.status_code < 400:
            body = profile.json()
            return [
                {
                    "customer_id": str(body.get("sub") or "linkedin"),
                    "manager_customer_id": None,
                    "account_name": body.get("name") or body.get("email") or "LinkedIn",
                    "currency_code": "",
                    "timezone": "",
                    "status": "ENABLED",
                }
            ]
        response.raise_for_status()
    elements = response.json().get("elements") or response.json().get("value") or []
    rows = []
    for item in elements:
        account_id = str(item.get("id") or item.get("account") or "")
        rows.append(
            {
                "customer_id": account_id.split(":")[-1] if account_id else "linkedin",
                "manager_customer_id": None,
                "account_name": item.get("name") or account_id or "LinkedIn",
                "currency_code": item.get("currency") or "",
                "timezone": "",
                "status": "ENABLED",
            }
        )
    return rows


def _discover_microsoft(access_token: str) -> list[dict]:
    profile = httpx.get(
        "https://graph.microsoft.com/v1.0/me",
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=30,
    )
    if profile.status_code >= 400:
        return [
            {
                "customer_id": "microsoft",
                "manager_customer_id": None,
                "account_name": "Microsoft Advertising",
                "currency_code": "",
                "timezone": "",
                "status": "ENABLED",
            }
        ]
    body = profile.json()
    return [
        {
            "customer_id": str(body.get("id") or "microsoft"),
            "manager_customer_id": None,
            "account_name": body.get("displayName") or body.get("mail") or "Microsoft Advertising",
            "currency_code": "",
            "timezone": "",
            "status": "ENABLED",
        }
    ]


def _discover_x(access_token: str) -> list[dict]:
    response = httpx.get(
        "https://api.twitter.com/2/users/me",
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=30,
    )
    response.raise_for_status()
    user = response.json().get("data") or {}
    return [
        {
            "customer_id": str(user.get("id") or "x"),
            "manager_customer_id": None,
            "account_name": user.get("name") or user.get("username") or "X",
            "currency_code": "",
            "timezone": "",
            "status": "ENABLED",
        }
    ]


def _discover_reddit(access_token: str) -> list[dict]:
    response = httpx.get(
        "https://oauth.reddit.com/api/v1/me",
        headers={"Authorization": f"Bearer {access_token}", "User-Agent": "google-ads-ai-reporting/1.0"},
        timeout=30,
    )
    response.raise_for_status()
    body = response.json()
    return [
        {
            "customer_id": str(body.get("id") or body.get("name") or "reddit"),
            "manager_customer_id": None,
            "account_name": body.get("name") or "Reddit",
            "currency_code": "",
            "timezone": "",
            "status": "ENABLED",
        }
    ]


def profile_identity(platform: str, access_token: str) -> tuple[str, str]:
    try:
        if platform == "meta":
            response = httpx.get(
                "https://graph.facebook.com/v21.0/me",
                params={"fields": "id,email,name"},
                headers={"Authorization": f"Bearer {access_token}"},
                timeout=30,
            )
            response.raise_for_status()
            body = response.json()
            return str(body.get("id") or ""), body.get("email") or body.get("name") or ""
        if platform == "microsoft":
            response = httpx.get(
                "https://graph.microsoft.com/v1.0/me",
                headers={"Authorization": f"Bearer {access_token}"},
                timeout=30,
            )
            response.raise_for_status()
            body = response.json()
            return str(body.get("id") or ""), body.get("mail") or body.get("userPrincipalName") or ""
        if platform == "linkedin":
            response = httpx.get(
                "https://api.linkedin.com/v2/userinfo",
                headers={"Authorization": f"Bearer {access_token}"},
                timeout=30,
            )
            response.raise_for_status()
            body = response.json()
            return str(body.get("sub") or ""), body.get("email") or body.get("name") or ""
        if platform == "x":
            response = httpx.get(
                "https://api.twitter.com/2/users/me",
                headers={"Authorization": f"Bearer {access_token}"},
                timeout=30,
            )
            response.raise_for_status()
            body = response.json().get("data") or {}
            return str(body.get("id") or ""), body.get("username") or body.get("name") or ""
        if platform == "reddit":
            response = httpx.get(
                "https://oauth.reddit.com/api/v1/me",
                headers={"Authorization": f"Bearer {access_token}", "User-Agent": "google-ads-ai-reporting/1.0"},
                timeout=30,
            )
            response.raise_for_status()
            body = response.json()
            return str(body.get("id") or ""), body.get("name") or ""
    except Exception:
        return platform, ""
    return platform, ""


def save_platform_accounts(
    session: Session,
    workspace_id: str,
    platform: str,
    token_body: dict,
) -> PlatformConnection:
    access_token = token_body.get("access_token") or ""
    refresh_token = token_body.get("refresh_token")
    external_user_id, external_email = profile_identity(platform, access_token) if access_token else (platform, "")
    if not external_user_id:
        external_user_id = platform
    expires_at = None
    if token_body.get("expires_in"):
        expires_at = datetime.now(UTC) + timedelta(seconds=int(token_body["expires_in"]))
    connection = session.scalar(
        select(PlatformConnection).where(
            PlatformConnection.workspace_id == workspace_id,
            PlatformConnection.platform == platform,
            PlatformConnection.external_user_id == external_user_id,
        )
    )
    if connection is None:
        connection = PlatformConnection(
            workspace_id=workspace_id,
            platform=platform,
            external_user_id=external_user_id,
            external_email=external_email,
            refresh_token_encrypted=encrypt_secret(refresh_token) if refresh_token else None,
            access_token_encrypted=encrypt_secret(access_token) if access_token else None,
            access_token_expires_at=expires_at,
            status="active",
        )
        session.add(connection)
    else:
        connection.external_email = external_email or connection.external_email
        if refresh_token:
            connection.refresh_token_encrypted = encrypt_secret(refresh_token)
        if access_token:
            connection.access_token_encrypted = encrypt_secret(access_token)
        connection.access_token_expires_at = expires_at
        connection.status = "active"
    session.flush()
    discovered = discover_accounts(platform, access_token) if access_token else []
    if not discovered:
        discovered = [
            {
                "customer_id": external_user_id,
                "manager_customer_id": None,
                "account_name": external_email or platform_spec(platform).label,
                "currency_code": "",
                "timezone": "",
                "status": "ENABLED",
            }
        ]
    for item in discovered:
        account = session.scalar(
            select(AdAccount).where(
                AdAccount.workspace_id == workspace_id,
                AdAccount.platform == platform,
                AdAccount.customer_id == item["customer_id"],
            )
        )
        if account is None:
            account = AdAccount(
                workspace_id=workspace_id,
                connection_id=None,
                platform_connection_id=connection.id,
                platform=platform,
                customer_id=item["customer_id"],
            )
            session.add(account)
            session.flush()
            session.add(AccountAnalyticsSettings(account_id=account.id))
        account.platform_connection_id = connection.id
        account.connection_id = None
        account.platform = platform
        account.manager_customer_id = item.get("manager_customer_id")
        account.account_name = item.get("account_name") or ""
        account.currency_code = item.get("currency_code") or ""
        account.timezone = item.get("timezone") or ""
        account.status = item.get("status") or "ENABLED"
    session.commit()
    return connection
