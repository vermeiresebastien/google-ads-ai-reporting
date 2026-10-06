from __future__ import annotations

from datetime import UTC, date, datetime

from gads.logging import get_logger
from gads.models import (
    Ad,
    AdAccount,
    AdGroup,
    AdGroupDaily,
    Campaign,
    CampaignBudgetDaily,
    CampaignDaily,
    ChangeEvent,
    Keyword,
    KeywordDaily,
    RawGoogleAdsRow,
    SearchTermDaily,
    SyncRun,
)
from sqlalchemy import select
from sqlalchemy.orm import Session

from gads_ingestion.google_ads.queries import (
    ad_group_metrics_query,
    ad_groups_query,
    ads_query,
    budgets_query,
    campaign_metrics_query,
    campaign_search_terms_query,
    campaigns_query,
    change_events_query,
    keyword_metrics_query,
    keywords_query,
    search_terms_query,
)
from gads_ingestion.mapping import (
    metric_block,
    num,
    optional_num,
    parse_date,
    parse_datetime,
    text_id,
)

logger = get_logger("gads.sync")


def _stats(fetched: int, inserted: int, updated: int, errors: int = 0, api_requests: int = 1) -> dict:
    status = "completed"
    if errors and (inserted or updated):
        status = "partial"
    elif errors and not inserted and not updated:
        status = "failed"
    return {
        "fetched": fetched,
        "inserted": inserted,
        "updated": updated,
        "errors": errors,
        "api_requests": api_requests,
        "status": status,
    }


def _store_raw(session: Session, account_id: str, dataset: str, resource_name: str, report_date: date, payload: dict) -> None:
    existing = session.scalar(
        select(RawGoogleAdsRow).where(
            RawGoogleAdsRow.account_id == account_id,
            RawGoogleAdsRow.dataset == dataset,
            RawGoogleAdsRow.google_resource_name == resource_name,
            RawGoogleAdsRow.report_date == report_date,
        )
    )
    if existing:
        existing.payload_json = payload
        existing.ingested_at = datetime.now(UTC)
        return
    session.add(
        RawGoogleAdsRow(
            account_id=account_id,
            dataset=dataset,
            google_resource_name=resource_name[:512],
            report_date=report_date,
            payload_json=payload,
        )
    )


def get_or_create_campaign(session: Session, account_id: str, google_id: str, **fields) -> tuple[Campaign, str]:
    google_id = text_id(google_id)
    row = session.scalar(
        select(Campaign).where(Campaign.account_id == account_id, Campaign.google_campaign_id == google_id)
    )
    if row:
        for key, value in fields.items():
            if value is not None:
                setattr(row, key, value)
        return row, "updated"
    row = Campaign(account_id=account_id, google_campaign_id=google_id, **{k: v for k, v in fields.items() if v is not None})
    session.add(row)
    session.flush()
    return row, "inserted"


def get_or_create_ad_group(session: Session, account_id: str, google_id: str, **fields) -> tuple[AdGroup, str]:
    google_id = text_id(google_id)
    row = session.scalar(
        select(AdGroup).where(AdGroup.account_id == account_id, AdGroup.google_ad_group_id == google_id)
    )
    if row:
        for key, value in fields.items():
            if value is not None:
                setattr(row, key, value)
        return row, "updated"
    row = AdGroup(account_id=account_id, google_ad_group_id=google_id, **fields)
    session.add(row)
    session.flush()
    return row, "inserted"


def run_tracked(session: Session, account: AdAccount, dataset: str, fn, start: date | None = None, end: date | None = None) -> SyncRun:
    started = datetime.now(UTC)
    run = SyncRun(
        account_id=account.id,
        dataset=dataset,
        status="running",
        started_at=started,
        start_date=start,
        end_date=end,
    )
    session.add(run)
    session.flush()
    try:
        stats = fn()
        run.status = stats["status"]
        run.rows_fetched = stats["fetched"]
        run.rows_inserted = stats["inserted"]
        run.rows_updated = stats["updated"]
        run.api_request_count = stats["api_requests"]
        run.completed_at = datetime.now(UTC)
        if stats["errors"]:
            run.error_message = f"{stats['errors']} row errors"
        if run.status in {"completed", "partial"}:
            account.last_successful_sync_at = run.completed_at
        logger.info(
            "sync_finished",
            workspace_id=account.workspace_id,
            account_id=account.id,
            dataset=dataset,
            start_date=start.isoformat() if start else None,
            end_date=end.isoformat() if end else None,
            duration_seconds=round((run.completed_at - started).total_seconds(), 3),
            rows_fetched=run.rows_fetched,
            rows_written=run.rows_inserted + run.rows_updated,
            status=run.status,
        )
    except Exception as exc:
        run.status = "failed"
        run.completed_at = datetime.now(UTC)
        run.error_message = str(exc)[:2000]
        logger.error(
            "sync_failed",
            workspace_id=account.workspace_id,
            account_id=account.id,
            dataset=dataset,
            error=run.error_message,
        )
        raise
    return run


def sync_campaigns(session: Session, account: AdAccount, client) -> dict:
    rows = client.search(account.customer_id, campaigns_query())
    inserted = updated = errors = 0
    today = date.today()
    for raw in rows:
        try:
            campaign = raw.get("campaign") or {}
            budget_micros = (raw.get("campaign_budget") or {}).get("amount_micros")
            _, action = get_or_create_campaign(
                session,
                account.id,
                campaign.get("id"),
                name=campaign.get("name") or "",
                status=campaign.get("status") or "",
                advertising_channel_type=campaign.get("advertising_channel_type") or "",
                campaign_type=campaign.get("advertising_channel_sub_type") or "",
                start_date=parse_date(campaign.get("start_date_time") or campaign.get("start_date")),
                end_date=parse_date(campaign.get("end_date_time") or campaign.get("end_date")),
                daily_budget=None if budget_micros is None else num(budget_micros) / 1_000_000,
            )
            _store_raw(session, account.id, "campaigns", campaign.get("resource_name") or f"campaign/{campaign.get('id')}", today, raw)
            inserted += action == "inserted"
            updated += action == "updated"
        except Exception:
            errors += 1
            logger.exception("campaign_row_failed", account_id=account.id)
    return _stats(len(rows), inserted, updated, errors)


def sync_ad_groups(session: Session, account: AdAccount, client) -> dict:
    rows = client.search(account.customer_id, ad_groups_query())
    inserted = updated = errors = 0
    today = date.today()
    for raw in rows:
        try:
            group = raw.get("ad_group") or {}
            campaign, _ = get_or_create_campaign(session, account.id, (raw.get("campaign") or {}).get("id"))
            _, action = get_or_create_ad_group(
                session,
                account.id,
                group.get("id"),
                campaign_id=campaign.id,
                name=group.get("name") or "",
                status=group.get("status") or "",
                type=group.get("type") or "",
            )
            _store_raw(session, account.id, "ad_groups", group.get("resource_name") or f"adgroup/{group.get('id')}", today, raw)
            inserted += action == "inserted"
            updated += action == "updated"
        except Exception:
            errors += 1
            logger.exception("ad_group_row_failed", account_id=account.id)
    return _stats(len(rows), inserted, updated, errors)


def sync_keywords(session: Session, account: AdAccount, client) -> dict:
    rows = client.search(account.customer_id, keywords_query())
    inserted = updated = errors = 0
    today = date.today()
    for raw in rows:
        try:
            criterion = raw.get("ad_group_criterion") or {}
            campaign, _ = get_or_create_campaign(session, account.id, (raw.get("campaign") or {}).get("id"))
            group, _ = get_or_create_ad_group(session, account.id, (raw.get("ad_group") or {}).get("id"), campaign_id=campaign.id)
            google_id = text_id(criterion.get("criterion_id"))
            existing = session.scalar(
                select(Keyword).where(
                    Keyword.account_id == account.id,
                    Keyword.ad_group_id == group.id,
                    Keyword.google_criterion_id == google_id,
                )
            )
            keyword_info = criterion.get("keyword") or {}
            quality = (criterion.get("quality_info") or {}).get("quality_score")
            fields = {
                "campaign_id": campaign.id,
                "keyword_text": keyword_info.get("text") or "",
                "match_type": keyword_info.get("match_type") or "",
                "status": criterion.get("status") or "",
                "quality_score": int(quality) if quality not in (None, "") else None,
            }
            if existing:
                for key, value in fields.items():
                    setattr(existing, key, value)
                action = "updated"
            else:
                session.add(Keyword(account_id=account.id, ad_group_id=group.id, google_criterion_id=google_id, **fields))
                action = "inserted"
            resource = criterion.get("resource_name") or f"keyword/{group.google_ad_group_id}~{google_id}"
            _store_raw(session, account.id, "keywords", resource, today, raw)
            inserted += action == "inserted"
            updated += action == "updated"
        except Exception:
            errors += 1
            logger.exception("keyword_row_failed", account_id=account.id)
    return _stats(len(rows), inserted, updated, errors)


def sync_ads(session: Session, account: AdAccount, client) -> dict:
    rows = client.search(account.customer_id, ads_query())
    inserted = updated = errors = 0
    today = date.today()
    for raw in rows:
        try:
            ad_group_ad = raw.get("ad_group_ad") or {}
            ad = ad_group_ad.get("ad") or {}
            campaign, _ = get_or_create_campaign(session, account.id, (raw.get("campaign") or {}).get("id"))
            group, _ = get_or_create_ad_group(session, account.id, (raw.get("ad_group") or {}).get("id"), campaign_id=campaign.id)
            google_id = text_id(ad.get("id"))
            rsa = ad.get("responsive_search_ad") or {}
            urls = ad.get("final_urls") or []
            fields = {
                "campaign_id": campaign.id,
                "ad_type": ad.get("type") or "",
                "status": ad_group_ad.get("status") or "",
                "final_url": urls[0] if urls else "",
                "headline_data": rsa.get("headlines"),
                "description_data": rsa.get("descriptions"),
            }
            existing = session.scalar(
                select(Ad).where(Ad.account_id == account.id, Ad.ad_group_id == group.id, Ad.google_ad_id == google_id)
            )
            if existing:
                for key, value in fields.items():
                    setattr(existing, key, value)
                action = "updated"
            else:
                session.add(Ad(account_id=account.id, ad_group_id=group.id, google_ad_id=google_id, **fields))
                action = "inserted"
            _store_raw(session, account.id, "ads", ad.get("resource_name") or f"ad/{google_id}", today, raw)
            inserted += action == "inserted"
            updated += action == "updated"
        except Exception:
            errors += 1
            logger.exception("ad_row_failed", account_id=account.id)
    return _stats(len(rows), inserted, updated, errors)


def _apply_metric_fields(target, metrics: dict) -> None:
    for key, value in metrics.items():
        setattr(target, key, value)
    for share_key in (
        "search_impression_share",
        "search_budget_lost_impression_share",
        "search_rank_lost_impression_share",
    ):
        if hasattr(target, share_key) and share_key not in metrics:
            continue


def sync_campaign_daily(session: Session, account: AdAccount, client, start: date, end: date) -> dict:
    rows = client.search(account.customer_id, campaign_metrics_query(start, end))
    inserted = updated = errors = 0
    for raw in rows:
        try:
            campaign_raw = raw.get("campaign") or {}
            day = parse_date((raw.get("segments") or {}).get("date"))
            if day is None:
                errors += 1
                continue
            campaign, _ = get_or_create_campaign(session, account.id, campaign_raw.get("id"))
            metrics = metric_block(raw.get("metrics"))
            source_metrics = raw.get("metrics") or {}
            metrics["search_impression_share"] = optional_num(source_metrics.get("search_impression_share"))
            metrics["search_budget_lost_impression_share"] = optional_num(source_metrics.get("search_budget_lost_impression_share"))
            metrics["search_rank_lost_impression_share"] = optional_num(source_metrics.get("search_rank_lost_impression_share"))
            existing = session.get(CampaignDaily, (account.id, day, campaign.id))
            if existing:
                _apply_metric_fields(existing, metrics)
                action = "updated"
            else:
                session.add(CampaignDaily(account_id=account.id, date=day, campaign_id=campaign.id, **metrics))
                action = "inserted"
            resource = f"{campaign_raw.get('resource_name') or campaign.google_campaign_id}:{day.isoformat()}"
            _store_raw(session, account.id, "campaign_daily", resource, day, raw)
            inserted += action == "inserted"
            updated += action == "updated"
        except Exception:
            errors += 1
            logger.exception("campaign_daily_row_failed", account_id=account.id)
    return _stats(len(rows), inserted, updated, errors)


def sync_ad_group_daily(session: Session, account: AdAccount, client, start: date, end: date) -> dict:
    rows = client.search(account.customer_id, ad_group_metrics_query(start, end))
    inserted = updated = errors = 0
    for raw in rows:
        try:
            day = parse_date((raw.get("segments") or {}).get("date"))
            if day is None:
                errors += 1
                continue
            campaign, _ = get_or_create_campaign(session, account.id, (raw.get("campaign") or {}).get("id"))
            group, _ = get_or_create_ad_group(
                session, account.id, (raw.get("ad_group") or {}).get("id"), campaign_id=campaign.id
            )
            metrics = metric_block(raw.get("metrics"))
            existing = session.get(AdGroupDaily, (account.id, day, group.id))
            fields = {**metrics, "campaign_id": campaign.id}
            if existing:
                _apply_metric_fields(existing, fields)
                action = "updated"
            else:
                session.add(AdGroupDaily(account_id=account.id, date=day, ad_group_id=group.id, **fields))
                action = "inserted"
            _store_raw(session, account.id, "ad_group_daily", f"adgroup/{group.google_ad_group_id}:{day.isoformat()}", day, raw)
            inserted += action == "inserted"
            updated += action == "updated"
        except Exception:
            errors += 1
            logger.exception("ad_group_daily_row_failed", account_id=account.id)
    return _stats(len(rows), inserted, updated, errors)


def _keyword_for(session: Session, account_id: str, group: AdGroup, google_criterion_id: str, campaign_id: str) -> Keyword:
    google_criterion_id = text_id(google_criterion_id)
    existing = session.scalar(
        select(Keyword).where(
            Keyword.account_id == account_id,
            Keyword.ad_group_id == group.id,
            Keyword.google_criterion_id == google_criterion_id,
        )
    )
    if existing:
        return existing
    row = Keyword(
        account_id=account_id,
        ad_group_id=group.id,
        campaign_id=campaign_id,
        google_criterion_id=google_criterion_id,
    )
    session.add(row)
    session.flush()
    return row


def sync_keyword_daily(session: Session, account: AdAccount, client, start: date, end: date) -> dict:
    rows = client.search(account.customer_id, keyword_metrics_query(start, end))
    inserted = updated = errors = 0
    for raw in rows:
        try:
            day = parse_date((raw.get("segments") or {}).get("date"))
            if day is None:
                errors += 1
                continue
            campaign, _ = get_or_create_campaign(session, account.id, (raw.get("campaign") or {}).get("id"))
            group, _ = get_or_create_ad_group(session, account.id, (raw.get("ad_group") or {}).get("id"), campaign_id=campaign.id)
            keyword = _keyword_for(
                session,
                account.id,
                group,
                (raw.get("ad_group_criterion") or {}).get("criterion_id"),
                campaign.id,
            )
            metrics = metric_block(raw.get("metrics"))
            existing = session.get(KeywordDaily, (account.id, day, keyword.id))
            fields = {**metrics, "campaign_id": campaign.id, "ad_group_id": group.id, "quality_score": keyword.quality_score}
            if existing:
                _apply_metric_fields(existing, fields)
                action = "updated"
            else:
                session.add(KeywordDaily(account_id=account.id, date=day, keyword_id=keyword.id, **fields))
                action = "inserted"
            _store_raw(session, account.id, "keyword_daily", f"keyword/{keyword.google_criterion_id}:{day.isoformat()}", day, raw)
            inserted += action == "inserted"
            updated += action == "updated"
        except Exception:
            errors += 1
            logger.exception("keyword_daily_row_failed", account_id=account.id)
    return _stats(len(rows), inserted, updated, errors)


def _upsert_search_term(session: Session, account: AdAccount, raw: dict, source: str) -> str:
    segments = raw.get("segments") or {}
    day = parse_date(segments.get("date"))
    if day is None:
        raise ValueError("search term row is missing a date")
    view_key = "search_term_view" if source == "ad_group" else "campaign_search_term_view"
    view = raw.get(view_key) or {}
    campaign, _ = get_or_create_campaign(session, account.id, (raw.get("campaign") or {}).get("id"))
    ad_group_google = (raw.get("ad_group") or {}).get("id")
    ad_group_id = ""
    if ad_group_google:
        group, _ = get_or_create_ad_group(session, account.id, ad_group_google, campaign_id=campaign.id)
        ad_group_id = group.id
    keyword_resource = ((segments.get("keyword") or {}).get("ad_group_criterion")) or ""
    match_type = segments.get("search_term_match_type") or ""
    search_term = view.get("search_term") or ""
    existing = session.scalar(
        select(SearchTermDaily).where(
            SearchTermDaily.account_id == account.id,
            SearchTermDaily.date == day,
            SearchTermDaily.source == source,
            SearchTermDaily.campaign_id == campaign.id,
            SearchTermDaily.ad_group_id == ad_group_id,
            SearchTermDaily.search_term == search_term,
            SearchTermDaily.keyword_resource == keyword_resource,
            SearchTermDaily.match_type == match_type,
        )
    )
    metrics = metric_block(raw.get("metrics"))
    if existing:
        _apply_metric_fields(existing, metrics)
        action = "updated"
    else:
        session.add(
            SearchTermDaily(
                account_id=account.id,
                date=day,
                source=source,
                campaign_id=campaign.id,
                ad_group_id=ad_group_id,
                search_term=search_term,
                keyword_resource=keyword_resource,
                match_type=match_type,
                **metrics,
            )
        )
        action = "inserted"
    resource = view.get("resource_name") or f"{source}:{search_term}:{day.isoformat()}:{keyword_resource}"
    _store_raw(session, account.id, "search_terms", resource[:512], day, raw)
    return action


def sync_search_terms(session: Session, account: AdAccount, client, start: date, end: date) -> dict:
    grouped = client.search(account.customer_id, search_terms_query(start, end))
    pmax = client.search(account.customer_id, campaign_search_terms_query(start, end))
    inserted = updated = errors = 0
    for source, rows in (("ad_group", grouped), ("campaign", pmax)):
        for raw in rows:
            try:
                action = _upsert_search_term(session, account, raw, source)
                inserted += action == "inserted"
                updated += action == "updated"
            except Exception:
                errors += 1
                logger.exception("search_term_row_failed", account_id=account.id)
    return _stats(len(grouped) + len(pmax), inserted, updated, errors, api_requests=2)


def sync_budgets(session: Session, account: AdAccount, client, start: date, end: date) -> dict:
    rows = client.search(account.customer_id, budgets_query(start, end))
    inserted = updated = errors = 0
    for raw in rows:
        try:
            day = parse_date((raw.get("segments") or {}).get("date"))
            if day is None:
                errors += 1
                continue
            campaign, _ = get_or_create_campaign(session, account.id, (raw.get("campaign") or {}).get("id"))
            metrics = raw.get("metrics") or {}
            budget = num((raw.get("campaign_budget") or {}).get("amount_micros")) / 1_000_000
            spend = num(metrics.get("cost_micros")) / 1_000_000
            fields = {
                "budget": budget,
                "spend": spend,
                "budget_utilization": None if budget == 0 else spend / budget,
                "impressions": int(num(metrics.get("impressions"))),
                "lost_impression_share_budget": optional_num(metrics.get("search_budget_lost_impression_share")),
            }
            existing = session.get(CampaignBudgetDaily, (account.id, day, campaign.id))
            if existing:
                for key, value in fields.items():
                    setattr(existing, key, value)
                action = "updated"
            else:
                session.add(CampaignBudgetDaily(account_id=account.id, date=day, campaign_id=campaign.id, **fields))
                action = "inserted"
            inserted += action == "inserted"
            updated += action == "updated"
        except Exception:
            errors += 1
            logger.exception("budget_row_failed", account_id=account.id)
    return _stats(len(rows), inserted, updated, errors)


def sync_change_events(session: Session, account: AdAccount, client, start: date, end: date) -> dict:
    rows = client.search(account.customer_id, change_events_query(start, end))
    inserted = updated = errors = 0
    for raw in rows:
        try:
            event = raw.get("change_event") or raw
            resource_name = event.get("resource_name") or ""
            existing = session.scalar(
                select(ChangeEvent).where(ChangeEvent.account_id == account.id, ChangeEvent.resource_name == resource_name)
            )
            changed = event.get("changed_fields")
            if isinstance(changed, dict):
                paths = changed.get("paths") or []
                changed_text = ",".join(paths)
            else:
                changed_text = str(changed or "")
            fields = {
                "event_timestamp": parse_datetime(event.get("change_date_time")) or datetime.now(UTC),
                "resource_type": event.get("change_resource_type") or "",
                "resource_changed_name": event.get("change_resource_name") or "",
                "change_type": event.get("resource_change_operation") or "",
                "field_changed": changed_text,
                "old_value": event.get("old_resource"),
                "new_value": event.get("new_resource"),
                "client_type": event.get("client_type") or "",
                "user_email": event.get("user_email") or "",
                "raw_payload": raw,
            }
            if existing:
                for key, value in fields.items():
                    setattr(existing, key, value)
                action = "updated"
            else:
                session.add(ChangeEvent(account_id=account.id, resource_name=resource_name, **fields))
                action = "inserted"
            inserted += action == "inserted"
            updated += action == "updated"
        except Exception:
            errors += 1
            logger.exception("change_event_row_failed", account_id=account.id)
    return _stats(len(rows), inserted, updated, errors)
