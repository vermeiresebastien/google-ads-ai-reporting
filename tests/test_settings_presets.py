from gads.models import AccountAnalyticsSettings
from gads_analytics.settings_presets import (
    apply_thresholds,
    delete_settings_preset,
    factory_values,
    list_settings_presets,
    save_settings_preset,
)
from report_fixture import seed_report_account


def test_factory_values_match_the_original_thresholds():
    values = factory_values()
    assert values["min_spend_for_waste"] == 50
    assert values["zero_conversion_min_spend"] == 25
    assert values["min_clicks"] == 10
    assert values["spend_anomaly_pct"] == 0.30
    assert values["min_spend_for_anomaly"] == 20


def test_reset_restores_factory_thresholds(session):
    seeded = seed_report_account(session)
    row = session.get(AccountAnalyticsSettings, seeded["account_id"])
    row.min_spend_for_anomaly = 1
    row.min_clicks = 99
    session.commit()

    apply_thresholds(row, factory_values())
    session.commit()

    assert float(row.min_spend_for_anomaly) == 20
    assert row.min_clicks == 10
    assert float(row.min_spend_for_waste) == 50


def test_preset_saves_and_applies_custom_thresholds(session):
    seeded = seed_report_account(session)
    account_id = seeded["account_id"]
    custom = factory_values()
    custom["min_clicks"] = 30
    custom["min_spend_for_anomaly"] = 1

    saved = save_settings_preset(session, account_id, "  Tight  ", custom)
    assert saved["name"] == "Tight"
    assert saved["values"]["min_clicks"] == 30

    updated = save_settings_preset(session, account_id, "Tight", {**custom, "min_clicks": 40})
    assert updated["id"] == saved["id"]
    assert list_settings_presets(session, account_id)[0]["values"]["min_clicks"] == 40

    row = session.get(AccountAnalyticsSettings, account_id)
    apply_thresholds(row, updated["values"])
    session.commit()
    assert row.min_clicks == 40
    assert float(row.min_spend_for_anomaly) == 1

    delete_settings_preset(session, account_id, saved["id"])
    assert list_settings_presets(session, account_id) == []
