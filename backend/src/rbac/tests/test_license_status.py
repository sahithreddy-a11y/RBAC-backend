from datetime import datetime, timedelta, timezone

from backend.src.rbac.license_status import evaluate_license


def test_perpetual_license_is_valid():
    now = datetime(2026, 8, 11, 12, 0, tzinfo=timezone.utc)

    result = evaluate_license(
        "active",
        "perpetual",
        now=now,
    )

    assert result.valid is True
    assert result.expired is False
    assert result.days_remaining is None
    assert result.show_warning is False
    assert result.reason == "perpetual"


def test_active_license_45_days_out_is_valid_without_warning():
    now = datetime(2026, 8, 11, 12, 0, tzinfo=timezone.utc)
    expiry = now + timedelta(days=45)

    result = evaluate_license(
        "active",
        expiry.isoformat(),
        now=now,
    )

    assert result.valid is True
    assert result.expired is False
    assert result.days_remaining == 45
    assert result.show_warning is False
    assert result.reason == "ok"


def test_active_license_10_days_out_shows_warning():
    now = datetime(2026, 8, 11, 12, 0, tzinfo=timezone.utc)
    expiry = now + timedelta(days=10)

    result = evaluate_license(
        "active",
        expiry.isoformat(),
        now=now,
    )

    assert result.valid is True
    assert result.expired is False
    assert result.days_remaining == 10
    assert result.show_warning is True
    assert result.reason == "ok"


def test_active_license_exactly_30_days_out_has_no_warning():
    now = datetime(2026, 8, 11, 12, 0, tzinfo=timezone.utc)
    expiry = now + timedelta(days=30)

    result = evaluate_license(
        "active",
        expiry.isoformat(),
        now=now,
    )

    assert result.valid is True
    assert result.expired is False
    assert result.days_remaining == 30
    assert result.show_warning is False
    assert result.reason == "ok"


def test_expired_license_is_invalid():
    now = datetime(2026, 8, 11, 12, 0, tzinfo=timezone.utc)
    expiry = now - timedelta(days=1)

    result = evaluate_license(
        "active",
        expiry.isoformat(),
        now=now,
    )

    assert result.valid is False
    assert result.expired is True
    assert result.days_remaining == 0
    assert result.show_warning is False
    assert result.reason == "expired"


def test_revoked_license_is_invalid_even_with_future_expiry():
    now = datetime(2026, 8, 11, 12, 0, tzinfo=timezone.utc)
    expiry = now + timedelta(days=365)

    result = evaluate_license(
        "revoked",
        expiry.isoformat(),
        now=now,
    )

    assert result.valid is False
    assert result.expired is False
    assert result.show_warning is False
    assert result.reason == "revoked"


def test_suspended_license_is_invalid_even_with_future_expiry():
    now = datetime(2026, 8, 11, 12, 0, tzinfo=timezone.utc)
    expiry = now + timedelta(days=365)

    result = evaluate_license(
        "suspended",
        expiry.isoformat(),
        now=now,
    )

    assert result.valid is False
    assert result.expired is False
    assert result.show_warning is False
    assert result.reason == "suspended"


def test_invalid_date_fails_closed():
    now = datetime(2026, 8, 11, 12, 0, tzinfo=timezone.utc)

    result = evaluate_license(
        "active",
        "not-a-date",
        now=now,
    )

    assert result.valid is False
    assert result.expired is False
    assert result.days_remaining is None
    assert result.show_warning is False
    assert result.reason == "invalid_date"


def test_none_expiry_is_perpetual():
    now = datetime(2026, 8, 11, 12, 0, tzinfo=timezone.utc)

    result = evaluate_license(
        "active",
        None,
        now=now,
    )

    assert result.valid is True
    assert result.expired is False
    assert result.days_remaining is None
    assert result.show_warning is False
    assert result.reason == "perpetual"


def test_license_expiring_in_one_hour_is_still_valid():
    now = datetime(2026, 8, 11, 23, 0, tzinfo=timezone.utc)
    expiry = datetime(2026, 8, 12, 0, 0, tzinfo=timezone.utc)

    result = evaluate_license(
        "active",
        expiry.isoformat(),
        now=now,
    )

    assert result.valid is True
    assert result.expired is False
    assert result.days_remaining == 0
    assert result.show_warning is True
    assert result.reason == "ok"


def test_date_only_expiring_today_remains_valid_until_day_end():
    now = datetime(2026, 8, 11, 12, 0, tzinfo=timezone.utc)

    result = evaluate_license(
        "active",
        "2026-08-11",
        now=now,
    )

    assert result.valid is True
    assert result.expired is False
    assert result.days_remaining == 0
    assert result.show_warning is True
    assert result.reason == "ok"


def test_license_expiring_exactly_now_is_expired():
    now = datetime(2026, 8, 11, 12, 0, tzinfo=timezone.utc)

    result = evaluate_license(
        "active",
        now.isoformat(),
        now=now,
    )

    assert result.valid is False
    assert result.expired is True
    assert result.days_remaining == 0
    assert result.show_warning is False
    assert result.reason == "expired"


def test_non_string_expiry_is_invalid_date():
    now = datetime(2026, 8, 11, 12, 0, tzinfo=timezone.utc)

    result = evaluate_license(
        "active",
        123456,
        now=now,
    )

    assert result.valid is False
    assert result.show_warning is False
    assert result.reason == "invalid_date"