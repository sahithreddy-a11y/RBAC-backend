from datetime import datetime, timedelta, timezone

from backend.src.rbac.activation_tokens import (
    check_activation_token,
    generate_activation_token,
    is_valid_token_format,
    token_expiry_from,
)


def test_generated_token_has_valid_format():
    token = generate_activation_token()

    assert is_valid_token_format(token)


def test_generated_tokens_are_unique():
    tokens = {generate_activation_token() for _ in range(10_000)}

    assert len(tokens) == 10_000


def test_none_record_returns_not_found():
    result = check_activation_token(None)

    assert result.valid is False
    assert result.reason == "not_found"


def test_used_token_is_rejected():
    now = datetime.now(timezone.utc)

    record = {
        "token": "BV-X7K2MP",
        "used": True,
        "expires_at": (now + timedelta(hours=1)).isoformat(),
    }

    result = check_activation_token(record, now=now)

    assert result.valid is False
    assert result.reason == "already_used"


def test_expired_token_is_rejected():
    now = datetime.now(timezone.utc)

    record = {
        "token": "BV-X7K2MP",
        "used": False,
        "expires_at": (now - timedelta(minutes=1)).isoformat(),
    }

    result = check_activation_token(record, now=now)

    assert result.valid is False
    assert result.reason == "expired"


def test_token_expiring_in_one_minute_is_valid():
    now = datetime.now(timezone.utc)

    record = {
        "token": "BV-X7K2MP",
        "used": False,
        "expires_at": (now + timedelta(minutes=1)).isoformat(),
    }

    result = check_activation_token(record, now=now)

    assert result.valid is True
    assert result.reason == "ok"


def test_lowercase_token_is_rejected():
    assert is_valid_token_format("bv-x7k2mp") is False


def test_malformed_token_is_rejected():
    assert is_valid_token_format("BV-ABC") is False
    assert is_valid_token_format("XX-X7K2MP") is False
    assert is_valid_token_format("BV-X7K2MP0") is False


def test_token_expiry_is_48_hours_later():
    created_at = datetime(
        2026,
        8,
        11,
        12,
        0,
        tzinfo=timezone.utc,
    )

    result = token_expiry_from(created_at)

    assert result == "2026-08-13T12:00:00+00:00"


def test_empty_token_is_rejected():
    assert is_valid_token_format("") is False


def test_non_string_token_is_rejected():
    assert is_valid_token_format(None) is False
    assert is_valid_token_format(123456) is False


def test_expired_at_exactly_now_is_rejected():
    now = datetime.now(timezone.utc)

    record = {
        "token": "BV-X7K2MP",
        "used": False,
        "expires_at": now.isoformat(),
    }

    result = check_activation_token(record, now=now)

    assert result.valid is False
    assert result.reason == "expired"


def test_missing_expiry_is_malformed():
    record = {
        "token": "BV-X7K2MP",
        "used": False,
    }

    result = check_activation_token(
        record,
        now=datetime.now(timezone.utc),
    )

    assert result.valid is False
    assert result.reason == "malformed"