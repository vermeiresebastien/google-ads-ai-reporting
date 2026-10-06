# Google Ads AI Reporting

An analytical layer for one or more Google Ads accounts. Ingestion writes idempotent facts to PostgreSQL. A deterministic analytics service answers period comparisons, campaign drivers, anomalies, wasted-spend candidates, and budget opportunities. ChatGPT and Claude reach that service through a REST API and an MCP server. They do not query the database, invent GAQL, or change the Google Ads account.

## Layout

- `apps/web` — Next.js dashboard
- `services/api` — FastAPI
- `services/ingestion` — Google Ads client, GAQL, and sync jobs
- `services/analytics` — metric math, anomalies, reports
- `services/mcp` — MCP tools that call the API
- `db/migrations` — Alembic schema and Postgres views
- `prompts/analyst.md` — analyst instructions

Google Ads API calls are isolated in `services/ingestion/gads_ingestion/google_ads` and target API **v25**.

## Local setup

```powershell
cd C:\Users\Sebastien\google-ads-ai-reporting
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
Copy-Item .env.example .env
```

Generate secrets and put them in `.env`:

```powershell
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

`TOKEN_ENCRYPTION_KEY` is the Fernet key. `JWT_SECRET` is the random string.

Start Postgres and Redis:

```powershell
docker compose up -d postgres redis
alembic upgrade head
```

The API and worker can run in Docker too (`docker compose up --build`). On Windows, run syncs from the CLI; the RQ worker is intended to run in the Linux container.

### API, worker, frontend

```powershell
uvicorn gads_api.main:app --reload
```

```powershell
cd apps\web
npm install
npm run dev
```

Open http://localhost:3000/login and create a workspace. Reporting starts after you connect a Google Ads account.

### Google Ads connection

1. Create a Google Cloud OAuth client and a Google Ads developer token.
2. Set `GOOGLE_ADS_DEVELOPER_TOKEN`, `GOOGLE_ADS_CLIENT_ID`, `GOOGLE_ADS_CLIENT_SECRET`, and the redirect URI `http://localhost:8000/api/google/oauth/callback`.
3. If you are connecting client accounts under a manager account, set `GOOGLE_ADS_LOGIN_CUSTOMER_ID`.
4. Sign in, open Accounts, and choose **Connect Google Ads**.

Queue an initial 90-day sync (requires Redis):

```powershell
python -m gads_ingestion.cli sync --account ACCOUNT_ID --mode initial --enqueue
```

Run the same sync in-process when Redis is not available:

```powershell
python -m gads_ingestion.cli sync --account ACCOUNT_ID --mode initial
```

`daily` refreshes the previous 7 days. `weekly` refreshes the previous 30 days. Change events are clamped to Google's 30-day window. Re-running a sync updates existing rows.

### MCP

Log in, then put the access token in `GADS_API_TOKEN`. Start the server over stdio:

```powershell
python -m gads_mcp.server
```

The tools call `/api/*`. They cannot run SQL or arbitrary GAQL.

### Tests

```powershell
pytest
ruff check shared services tests
```

### Reconciliation

```powershell
python -m gads_ingestion.cli reconcile --account ACCOUNT_ID
```

## Deployment

- Frontend: Vercel, with `NEXT_PUBLIC_API_URL` pointing at the API.
- API and worker: the root `Dockerfile`. Command `api` migrates and serves FastAPI. Command `worker` runs the RQ worker. Set secrets in the host, not in git.
- Optional `SENTRY_DSN` enables Sentry. Optional `OPENAI_API_KEY` lets `POST /api/ai/query` summarize tool output. Without it, the API still writes the report from the same numbers.

## Assumptions

- Authentication is an app-owned user table and JWT, so local Docker does not need Supabase. Every analytical query still checks user, workspace, and account.
- Money is stored as `cost_micros` and numeric `cost`. Ratios are computed in the analytics layer.
- `search_term_view` excludes Performance Max, so search-term sync also reads `campaign_search_term_view` and marks `source`.
- V1 does not change campaigns, bids, budgets, keywords, or ads.
