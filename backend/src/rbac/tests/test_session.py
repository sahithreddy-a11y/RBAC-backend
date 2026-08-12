from datetime import datetime, timedelta, timezone

from backend.src.rbac.session import (
    OFFLINE_GRACE_PERIOD,
    REFRESH_TOKEN_LIFETIME,
    evaluate_session,
)


NOW = datetime(2026, 8, 12, 10, 0, 0, tzinfo=timezone.utc)


def test_valid_access_token_proceeds_even_when_offline():
    event = evaluate_session(
        access_token_expires_at=NOW + timedelta(minutes=30),
        refresh_token_issued_at=NOW - timedelta(days=5),
        last_successful_online_check=NOW - timedelta(days=5),
        is_online=False,
        now=NOW,
    )

    assert event.action == "proceed"
    assert event.reason == "access_token_valid"
    assert event.offline_days_remaining is None


def test_expired_access_token_online_requires_refresh():
    event = evaluate_session(
        access_token_expires_at=NOW - timedelta(minutes=1),
        refresh_token_issued_at=NOW - timedelta(days=5),
        last_successful_online_check=NOW - timedelta(days=5),
        is_online=True,
        now=NOW,
    )

    assert event.action == "refresh_required"
    assert event.reason == "access_token_expired"
    assert event.offline_days_remaining is None


def test_expired_access_token_offline_within_grace_proceeds():
    event = evaluate_session(
        access_token_expires_at=NOW - timedelta(minutes=1),
        refresh_token_issued_at=NOW - timedelta(days=5),
        last_successful_online_check=NOW - timedelta(days=3),
        is_online=False,
        now=NOW,
    )

    assert event.action == "proceed"
    assert event.reason == "offline_grace_active"
    assert event.offline_days_remaining == 4


def test_expired_access_token_offline_after_grace_requires_reconnect():
    event = evaluate_session(
        access_token_expires_at=NOW - timedelta(minutes=1),
        refresh_token_issued_at=NOW - timedelta(days=5),
        last_successful_online_check=NOW - timedelta(days=8),
        is_online=False,
        now=NOW,
    )

    assert event.action == "reconnect_required"
    assert event.reason == "offline_grace_expired"
    assert event.offline_days_remaining == 0


def test_refresh_token_older_than_30_days_requires_login_online():
    event = evaluate_session(
        access_token_expires_at=NOW - timedelta(minutes=1),
        refresh_token_issued_at=NOW - timedelta(days=31),
        last_successful_online_check=NOW - timedelta(days=1),
        is_online=True,
        now=NOW,
    )

    assert event.action == "login_required"
    assert event.reason == "refresh_token_expired"


def test_refresh_token_older_than_30_days_requires_login_offline():
    event = evaluate_session(
        access_token_expires_at=NOW - timedelta(minutes=1),
        refresh_token_issued_at=NOW - timedelta(days=31),
        last_successful_online_check=NOW - timedelta(days=1),
        is_online=False,
        now=NOW,
    )

    assert event.action == "login_required"
    assert event.reason == "refresh_token_expired"


def test_refresh_token_31_days_old_requires_login_even_with_recent_online_check():
    event = evaluate_session(
        access_token_expires_at=NOW - timedelta(minutes=1),
        refresh_token_issued_at=NOW - timedelta(days=31),
        last_successful_online_check=NOW - timedelta(days=1),
        is_online=False,
        now=NOW,
    )

    assert event.action == "login_required"


def test_never_successfully_online_requires_login_when_offline():
    event = evaluate_session(
        access_token_expires_at=NOW - timedelta(minutes=1),
        refresh_token_issued_at=NOW - timedelta(days=5),
        last_successful_online_check=None,
        is_online=False,
        now=NOW,
    )

    assert event.action == "login_required"
    assert event.reason == "no_successful_online_check"


def test_future_online_check_requires_reconnect():
    event = evaluate_session(
        access_token_expires_at=NOW - timedelta(minutes=1),
        refresh_token_issued_at=NOW - timedelta(days=5),
        last_successful_online_check=NOW + timedelta(days=1),
        is_online=False,
        now=NOW,
    )

    assert event.action == "reconnect_required"
    assert event.reason == "invalid_future_online_check"


def test_exactly_seven_days_of_offline_grace_is_still_allowed():
    event = evaluate_session(
        access_token_expires_at=NOW - timedelta(minutes=1),
        refresh_token_issued_at=NOW - timedelta(days=5),
        last_successful_online_check=NOW - OFFLINE_GRACE_PERIOD,
        is_online=False,
        now=NOW,
    )

    assert event.action == "proceed"
    assert event.reason == "offline_grace_active"
    assert event.offline_days_remaining == 0


def test_more_than_seven_days_offline_requires_reconnect():
    event = evaluate_session(
        access_token_expires_at=NOW - timedelta(minutes=1),
        refresh_token_issued_at=NOW - timedelta(days=7, seconds=1),
        last_successful_online_check=NOW - timedelta(days=7, seconds=1),
        is_online=False,
        now=NOW,
    )

    assert event.action == "reconnect_required"


def test_exactly_30_days_old_refresh_token_requires_login():
    event = evaluate_session(
        access_token_expires_at=NOW - timedelta(minutes=1),
        refresh_token_issued_at=NOW - REFRESH_TOKEN_LIFETIME,
        last_successful_online_check=NOW - timedelta(days=1),
        is_online=True,
        now=NOW,
    )

    assert event.action == "login_required"
    assert event.reason == "refresh_token_expired"


def test_missing_refresh_token_online_requires_login():
    event = evaluate_session(
        access_token_expires_at=NOW - timedelta(minutes=1),
        refresh_token_issued_at=None,
        last_successful_online_check=NOW - timedelta(days=1),
        is_online=True,
        now=NOW,
    )

    assert event.action == "login_required"
    assert event.reason == "refresh_token_missing"


def test_naive_datetimes_are_treated_as_utc():
    naive_now = datetime(2026, 8, 12, 10, 0, 0)

    event = evaluate_session(
        access_token_expires_at=naive_now + timedelta(minutes=30),
        refresh_token_issued_at=naive_now - timedelta(days=5),
        last_successful_online_check=naive_now - timedelta(days=5),
        is_online=False,
        now=naive_now,
    )

    assert event.action == "proceed"
    assert event.reason == "access_token_valid"


def test_timezone_aware_datetimes_are_normalized_to_utc():
    ist = timezone(timedelta(hours=5, minutes=30))

    local_now = datetime(2026, 8, 12, 15, 30, tzinfo=ist)

    event = evaluate_session(
        access_token_expires_at=local_now - timedelta(minutes=1),
        refresh_token_issued_at=local_now - timedelta(days=5),
        last_successful_online_check=local_now - timedelta(days=3),
        is_online=False,
        now=local_now,
    )

    assert event.action == "proceed"
    assert event.offline_days_remaining == 4