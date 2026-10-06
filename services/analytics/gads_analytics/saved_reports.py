from __future__ import annotations

import hashlib
import io
import re
import zipfile
from collections import defaultdict
from datetime import date, timedelta

from gads.models import SavedReport, SavedReportHighlight, utcnow
from sqlalchemy import inspect, select, text
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.orm import Session

HIGHLIGHT_COLORS = ("yellow", "green", "blue", "pink")


def ensure_saved_reports_table(session: Session) -> None:
    bind = session.get_bind()
    SavedReport.__table__.create(bind=bind, checkfirst=True)
    SavedReportHighlight.__table__.create(bind=bind, checkfirst=True)
    columns = {column["name"] for column in inspect(bind).get_columns(SavedReport.__tablename__)}
    if "title" not in columns:
        try:
            session.execute(text("ALTER TABLE saved_reports ADD COLUMN title VARCHAR(200) NOT NULL DEFAULT ''"))
            session.commit()
        except (OperationalError, ProgrammingError):
            session.rollback()


def save_report_summary(session: Session, account_id: str, report: dict, body: str, question: str = "") -> None:
    if not body.strip():
        return
    ensure_saved_reports_table(session)
    report_date = date.fromisoformat(str(report["date"]))
    period = (report.get("comparison") or {}).get("period") or {}
    kind = _summary_kind(period.get("kind"), question)
    existing = session.scalar(
        select(SavedReport).where(
            SavedReport.account_id == account_id,
            SavedReport.report_date == report_date,
            SavedReport.kind == kind,
        )
    )
    start = _parse_date(period.get("current_start"))
    end = _parse_date(period.get("current_end"))
    if existing is None:
        session.add(
            SavedReport(
                account_id=account_id,
                report_date=report_date,
                kind=kind,
                period_start=start,
                period_end=end,
                question=question,
                body=body,
            )
        )
    else:
        existing.period_start = start
        existing.period_end = end
        existing.question = question
        existing.body = body
        existing.updated_at = utcnow()
    session.commit()


def save_trend_summary(session: Session, account_id: str, start: date, end: date, question: str, body: str) -> str | None:
    if not body.strip():
        return None
    ensure_saved_reports_table(session)
    kind = _trend_kind(question, start, end)
    existing = session.scalar(
        select(SavedReport).where(
            SavedReport.account_id == account_id,
            SavedReport.report_date == end,
            SavedReport.kind == kind,
        )
    )
    if existing is None:
        existing = SavedReport(
            account_id=account_id,
            report_date=end,
            kind=kind,
            period_start=start,
            period_end=end,
            question=question,
            body=body,
        )
        session.add(existing)
        session.flush()
    else:
        existing.period_start = start
        existing.period_end = end
        existing.question = question
        existing.body = body
        existing.updated_at = utcnow()
    saved_id = existing.id
    session.commit()
    return saved_id


def trend_notes_zip(session: Session, account_id: str, start: date, end: date) -> tuple[bytes, str]:
    ensure_saved_reports_table(session)
    rows = [
        row
        for row in session.scalars(
            select(SavedReport)
            .where(SavedReport.account_id == account_id, SavedReport.kind.like("trend:%"))
            .order_by(SavedReport.period_start, SavedReport.updated_at)
        ).all()
        if _overlaps(row, start, end)
    ]
    if not rows:
        raise ValueError("No saved trend covers this period")
    used: set[str] = set()
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for row in rows:
            label = (row.title or "").strip() or (row.question or "").strip() or "Long-term overview"
            day = (row.period_start or row.report_date).isoformat()
            name = f"{day}-{_file_slug(label)}-full.txt"
            if name in used:
                name = f"{day}-{_file_slug(label)}-{row.id[:8]}-full.txt"
            used.add(name)
            archive.writestr(name, row.body or "")
    filename = f"{start.isoformat()}-trends.zip" if start == end else f"{start.isoformat()}-to-{end.isoformat()}-trends.zip"
    return buffer.getvalue(), filename


def list_saved_reports(session: Session, account_id: str) -> list[dict]:
    ensure_saved_reports_table(session)
    rows = session.scalars(
        select(SavedReport)
        .where(SavedReport.account_id == account_id)
        .order_by(SavedReport.report_date.desc(), SavedReport.updated_at.desc())
        .limit(200)
    ).all()
    grouped = _highlights_for(session, [row.id for row in rows])
    return [
        {
            "id": row.id,
            "report_date": row.report_date.isoformat(),
            "kind": row.kind,
            "period_start": row.period_start.isoformat() if row.period_start else None,
            "period_end": row.period_end.isoformat() if row.period_end else None,
            "question": row.question,
            "title": row.title or "",
            "body": row.body,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
            "highlights": grouped[row.id],
        }
        for row in rows
    ]


def add_saved_highlight(session: Session, account_id: str, report_id: str, quote: str, color: str, note: str = "") -> dict:
    ensure_saved_reports_table(session)
    row = session.scalar(select(SavedReport).where(SavedReport.id == report_id, SavedReport.account_id == account_id))
    if row is None:
        raise LookupError("Saved summary was not found")
    if color not in HIGHLIGHT_COLORS:
        raise ValueError("Choose yellow, green, blue, or pink")
    cleaned = quote.strip()
    parts = [part.strip() for part in cleaned.splitlines() if part.strip()]
    if not parts or len(cleaned) > 2000 or any(len(part) > 1000 for part in parts):
        raise ValueError("Select a shorter passage from the summary")
    if any(not _contains_quote(row.body, part) for part in parts):
        raise ValueError("That text is not in this summary")
    item = SavedReportHighlight(saved_report_id=row.id, quote=cleaned, color=color, note=note.strip()[:500])
    session.add(item)
    session.commit()
    return _highlight_payload(item)


def delete_saved_highlight(session: Session, account_id: str, report_id: str, highlight_id: str) -> bool:
    ensure_saved_reports_table(session)
    row = session.scalar(select(SavedReport).where(SavedReport.id == report_id, SavedReport.account_id == account_id))
    if row is None:
        return False
    item = session.scalar(
        select(SavedReportHighlight).where(
            SavedReportHighlight.id == highlight_id,
            SavedReportHighlight.saved_report_id == row.id,
        )
    )
    if item is None:
        return False
    session.delete(item)
    session.commit()
    return True


def rename_saved_report(session: Session, account_id: str, report_id: str, title: str) -> dict | None:
    return update_saved_report(session, account_id, report_id, title=title)


def update_saved_report(
    session: Session,
    account_id: str,
    report_id: str,
    title: str | None = None,
    body: str | None = None,
) -> dict | None:
    ensure_saved_reports_table(session)
    row = session.scalar(select(SavedReport).where(SavedReport.id == report_id, SavedReport.account_id == account_id))
    if row is None:
        return None
    if title is None and body is None:
        raise ValueError("Change the title or the note.")
    if title is not None:
        cleaned = " ".join(title.split()).strip()
        if len(cleaned) > 200:
            raise ValueError("Enter a shorter title")
        row.title = cleaned
    if body is not None:
        cleaned_body = body.replace("\r\n", "\n")
        if len(cleaned_body) > 200_000:
            raise ValueError("That note is too long.")
        row.body = cleaned_body
    row.updated_at = utcnow()
    session.commit()
    return {"id": row.id, "title": row.title, "body": row.body}


def delete_saved_report(session: Session, account_id: str, report_id: str) -> bool:
    ensure_saved_reports_table(session)
    row = session.scalar(
        select(SavedReport).where(SavedReport.id == report_id, SavedReport.account_id == account_id)
    )
    if row is None:
        return False
    for item in session.scalars(select(SavedReportHighlight).where(SavedReportHighlight.saved_report_id == row.id)).all():
        session.delete(item)
    session.delete(row)
    session.commit()
    return True


def day_change_zip(session: Session, account, start: date, end: date) -> tuple[bytes, str]:
    from gads_analytics.narrative import render_day_change
    from gads_analytics.repository import build_report

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        day = start
        while day <= end:
            report = build_report(session, account, "today_vs_yesterday", day)
            yesterday = day - timedelta(days=1)
            archive.writestr(f"{yesterday.isoformat()} to {day.isoformat()}.txt", render_day_change(report))
            day += timedelta(days=1)
    if start == end:
        filename = f"{(start - timedelta(days=1)).isoformat()} to {start.isoformat()}.zip"
    else:
        filename = f"{start.isoformat()} to {end.isoformat()}.zip"
    return buffer.getvalue(), filename


def _highlights_for(session: Session, report_ids: list[str]) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = defaultdict(list)
    if not report_ids:
        return grouped
    rows = session.scalars(
        select(SavedReportHighlight)
        .where(SavedReportHighlight.saved_report_id.in_(report_ids))
        .order_by(SavedReportHighlight.created_at)
    ).all()
    for row in rows:
        grouped[row.saved_report_id].append(_highlight_payload(row))
    return grouped


def _highlight_payload(row: SavedReportHighlight) -> dict:
    return {
        "id": row.id,
        "quote": row.quote,
        "color": row.color,
        "note": row.note,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def _contains_quote(body: str, quote: str) -> bool:
    def loose(value: str) -> str:
        letters = "".join(char if char.isalnum() or char.isspace() else " " for char in value)
        return " ".join(letters.split()).casefold()

    return loose(quote) in loose(body)


def _trend_kind(question: str, start: date, end: date) -> str:
    text = f"{question.strip().casefold()}|{start.isoformat()}|{end.isoformat()}"
    digest = hashlib.sha256(text.encode()).hexdigest()[:12]
    return f"trend:{digest}"


def _file_slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug[:80] or "summary"


def _overlaps(row: SavedReport, start: date, end: date) -> bool:
    item_start = row.period_start or row.report_date
    item_end = row.period_end or row.report_date
    return item_start <= end and item_end >= start


def _summary_kind(period_kind, question: str) -> str:
    if question.strip():
        digest = hashlib.sha256(question.strip().casefold().encode()).hexdigest()[:12]
        return f"ask:{digest}"
    return str(period_kind or "report")


def _parse_date(value) -> date | None:
    if not value:
        return None
    return date.fromisoformat(str(value))
