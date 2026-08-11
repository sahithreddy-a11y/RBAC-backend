from datetime import datetime, timezone
from uuid import UUID

import pytest

from backend.src.rbac.audit import EVENT_TYPES, build_audit_event


def test_build_audit_event_returns_expected_fields():
    now = datetime(2026, 8, 11, 10, 30, 0, tzinfo=timezone.utc)

    event = build_audit_event(
        "LOGIN",
        user_id="user-123",
        org_id="org-456",
        license_id="lic-789",
        module_id="fcs",
        ip_address="10.0.0.1",
        user_agent="TestClient/1.0",
        success=True,
        metadata={"method": "password"},
        now=now,
    )

    assert event["event_type"] == "LOGIN"
    assert event["user_id"] == "user-123"
    assert event["org_id"] == "org-456"
    assert event["license_id"] == "lic-789"
    assert event["module_id"] == "fcs"
    assert event["ip_address"] == "10.0.0.1"
    assert event["user_agent"] == "TestClient/1.0"
    assert event["success"] is True
    assert event["metadata"] == {"method": "password"}
    assert event["timestamp"] == "2026-08-11T10:30:00+00:00"


def test_event_id_is_valid_uuid4():
    event = build_audit_event(
        "LOGIN",
        user_id="user-123",
    )

    event_id = UUID(event["event_id"])

    assert event_id.version == 4


def test_two_events_have_different_event_ids():
    event_one = build_audit_event(
        "LOGIN",
        user_id="user-123",
    )

    event_two = build_audit_event(
        "LOGIN",
        user_id="user-123",
    )

    assert event_one["event_id"] != event_two["event_id"]


def test_invalid_event_type_raises_value_error():
    with pytest.raises(ValueError):
        build_audit_event(
            "HACKING",
            user_id="user-123",
        )


def test_all_defined_event_types_are_accepted():
    for event_type in EVENT_TYPES:
        event = build_audit_event(
            event_type,
            user_id="user-123",
        )

        assert event["event_type"] == event_type


def test_password_is_redacted():
    event = build_audit_event(
        "LOGIN",
        user_id="user-123",
        metadata={"password": "hunter2"},
    )

    assert event["metadata"]["password"] == "[REDACTED]"


def test_sensitive_keys_are_case_insensitive():
    event = build_audit_event(
        "LOGIN",
        user_id="user-123",
        metadata={"PassWord": "hunter2"},
    )

    assert event["metadata"]["PassWord"] == "[REDACTED]"


def test_nested_authorization_is_redacted():
    event = build_audit_event(
        "LOGIN",
        user_id="user-123",
        metadata={
            "request": {
                "headers": {
                    "Authorization": "Bearer secret-token"
                }
            }
        },
    )

    assert (
        event["metadata"]["request"]["headers"]["Authorization"]
        == "[REDACTED]"
    )


def test_non_sensitive_metadata_is_preserved():
    metadata = {
        "module": "fcs",
        "decision": "allow",
        "attempt": 3,
    }

    event = build_audit_event(
        "MODULE_ACCESS_CHANGE",
        user_id="user-123",
        metadata=metadata,
    )

    assert event["metadata"] == metadata


def test_metadata_none_does_not_crash():
    event = build_audit_event(
        "LOGIN",
        user_id="user-123",
        metadata=None,
    )

    assert event["metadata"] == {}


def test_original_metadata_is_not_mutated():
    metadata = {
        "username": "user-123",
        "password": "hunter2",
        "request": {
            "headers": {
                "Authorization": "Bearer secret-token"
            }
        },
    }

    original_metadata = {
        "username": "user-123",
        "password": "hunter2",
        "request": {
            "headers": {
                "Authorization": "Bearer secret-token"
            }
        },
    }

    event = build_audit_event(
        "LOGIN",
        user_id="user-123",
        metadata=metadata,
    )

    assert metadata == original_metadata
    assert event["metadata"]["password"] == "[REDACTED]"
    assert (
        event["metadata"]["request"]["headers"]["Authorization"]
        == "[REDACTED]"
    )


def test_timestamp_is_converted_to_utc():
    local_time = datetime(
        2026,
        8,
        11,
        15,
        30,
        tzinfo=timezone.utc,
    )

    event = build_audit_event(
        "LOGIN",
        user_id="user-123",
        now=local_time,
    )

    parsed_timestamp = datetime.fromisoformat(event["timestamp"])

    assert parsed_timestamp.tzinfo is not None
    assert parsed_timestamp.utcoffset().total_seconds() == 0