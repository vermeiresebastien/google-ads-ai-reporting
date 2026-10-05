"""Initial analytical schema and Postgres views."""

from pathlib import Path

from alembic import op

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None

VIEW_NAMES = (
    "account_performance_daily",
    "campaign_performance_daily",
    "keyword_performance_daily",
    "search_term_performance_daily",
    "recent_changes",
    "budget_opportunities",
    "wasted_spend",
    "performance_anomalies",
)


def upgrade() -> None:
    from gads.models import Base

    bind = op.get_bind()
    Base.metadata.create_all(bind=bind)
    if bind.dialect.name == "postgresql":
        sql_path = Path(__file__).resolve().parents[2] / "views" / "analytics.sql"
        op.execute(sql_path.read_text(encoding="utf-8"))


def downgrade() -> None:
    from gads.models import Base

    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("DROP FUNCTION IF EXISTS campaign_period_comparison(text, date, date, date, date)")
        for name in VIEW_NAMES:
            op.execute(f"DROP VIEW IF EXISTS {name}")
    Base.metadata.drop_all(bind=bind)
