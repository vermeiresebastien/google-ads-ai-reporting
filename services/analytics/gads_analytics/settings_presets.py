from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from gads.models import AccountAnalyticsSettings, SettingsPreset
from sqlalchemy import select
from sqlalchemy.orm import Session

from gads_analytics.analysis import Thresholds

THRESHOLD_KEYS = (
    "min_spend_for_waste",
    "spend_anomaly_pct",
    "cpa_anomaly_pct",
    "roas_anomaly_pct",
    "conversion_anomaly_pct",
    "cpc_anomaly_pct",
    "cvr_anomaly_pct",
    "zero_conversion_min_spend",
    "budget_lost_is_min",
    "min_clicks",
    "min_spend_for_anomaly",
)
MAX_PRESETS = 30


class PresetNotFound(LookupError):
    pass


def factory_values() -> dict[str, float | int]:
    defaults = Thresholds()
    return {key: getattr(defaults, key) for key in THRESHOLD_KEYS}


def normalize_thresholds(values: dict) -> dict[str, float | int]:
    normalized: dict[str, float | int] = {}
    for key in THRESHOLD_KEYS:
        if key not in values or values[key] is None:
            raise ValueError("Every threshold is required.")
        number = int(values[key]) if key == "min_clicks" else float(values[key])
        if number < 0:
            raise ValueError("Thresholds cannot be negative.")
        normalized[key] = number
    return normalized


def apply_thresholds(row: AccountAnalyticsSettings, values: dict) -> None:
    for key, value in normalize_thresholds(values).items():
        setattr(row, key, value if key == "min_clicks" else Decimal(str(value)))
    row.updated_at = datetime.now(UTC)


def ensure_settings_presets_table(session: Session) -> None:
    SettingsPreset.__table__.create(bind=session.get_bind(), checkfirst=True)


def list_settings_presets(session: Session, account_id: str) -> list[dict]:
    ensure_settings_presets_table(session)
    rows = session.scalars(
        select(SettingsPreset).where(SettingsPreset.account_id == account_id).order_by(SettingsPreset.name)
    ).all()
    return [_preset_payload(row) for row in rows]


def save_settings_preset(session: Session, account_id: str, name: str, values: dict) -> dict:
    ensure_settings_presets_table(session)
    label = name.strip()
    if not label or len(label) > 80:
        raise ValueError("Name the preset with 80 characters or fewer.")
    stored = normalize_thresholds(values)
    existing = session.scalar(
        select(SettingsPreset).where(SettingsPreset.account_id == account_id, SettingsPreset.name == label)
    )
    if existing is None:
        count = len(
            session.scalars(select(SettingsPreset.id).where(SettingsPreset.account_id == account_id)).all()
        )
        if count >= MAX_PRESETS:
            raise ValueError("You can save 30 presets.")
        existing = SettingsPreset(account_id=account_id, name=label, values=stored)
        session.add(existing)
    else:
        existing.values = stored
        existing.updated_at = datetime.now(UTC)
    session.commit()
    return _preset_payload(existing)


def delete_settings_preset(session: Session, account_id: str, preset_id: str) -> None:
    ensure_settings_presets_table(session)
    row = session.scalar(
        select(SettingsPreset).where(SettingsPreset.account_id == account_id, SettingsPreset.id == preset_id)
    )
    if row is None:
        raise PresetNotFound
    session.delete(row)
    session.commit()


def load_settings_preset(session: Session, account_id: str, preset_id: str) -> dict:
    ensure_settings_presets_table(session)
    row = session.scalar(
        select(SettingsPreset).where(SettingsPreset.account_id == account_id, SettingsPreset.id == preset_id)
    )
    if row is None:
        raise PresetNotFound
    return _preset_payload(row)


def _preset_payload(row: SettingsPreset) -> dict:
    return {"id": row.id, "name": row.name, "values": normalize_thresholds(row.values)}
