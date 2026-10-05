# Product contract

This repository implements the Google Ads AI Reporting v1 specification.

The product is a queryable analyst:

Google Ads → Google Ads API v25 → ingestion jobs → PostgreSQL → analytical calculations → FastAPI and MCP → ChatGPT / Claude.

The model interprets tool results. It does not calculate core metrics, query raw tables, generate arbitrary GAQL, or mutate the ad account.

## V1 includes

- Multi-tenant users, workspaces, Google connections, and ad accounts. V1 operation can start with one account.
- OAuth, encrypted refresh tokens, and account discovery including manager accounts.
- Idempotent sync for campaigns, ad groups, keywords, ads, daily performance, search terms (including Performance Max), budgets, and change events.
- Raw payloads, sync runs, and configurable schedules: initial 90 days, daily 7-day refresh, weekly 30-day refresh.
- Period comparisons, campaign drivers, anomalies, wasted-spend candidates, and budget opportunities. Thresholds live on `account_analytics_settings`.
- Authenticated REST tools and an MCP server with row and date limits.
- A daily report and a deterministic narrative. OpenAI summarization is optional.
- A read-only dashboard for performance, accounts, campaigns, search terms, changes, reports, and settings.

## V1 excludes

Automatic campaign, bid, budget, keyword, or ad changes. Meta Ads, GA4, Shopify, CRM, predictive ML, vector search, BigQuery, and Kubernetes.

## Freshness and evidence

Reports include `data_freshness`. Recommendations are attached to evidence from the analytical tools. Zero conversions are not labeled waste unless spend and click thresholds are met. Budget lost impression share is not a budget recommendation unless efficiency is also acceptable.
