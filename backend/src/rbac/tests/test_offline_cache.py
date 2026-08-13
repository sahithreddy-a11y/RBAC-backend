from datetime import datetime, timedelta, timezone

from backend.src.rbac.offline_cache import (
    open_cache,
    seal_cache,
)


SECRET = b"test-secret"

NOW = datetime(
    2026,
    8,
    13,
    12,
    0,
    tzinfo=timezone.utc,
)


def test_round_trip():
    payload = {
        "license_id": "lic-123",
        "license_status": "active",
        "license_expires": "2026-08-20T00:00:00+00:00",
    }

    sealed = seal_cache(
        payload,
        secret=SECRET,
        now=NOW,
    )

    result = open_cache(
        sealed,
        secret=SECRET,
        now=NOW,
    )

    assert result.ok is True
    assert result.reason == "valid"
    assert result.payload == payload


def test_modified_payload_is_rejected():
    payload = {
        "license_id": "lic-123",
        "license_status": "active",
    }

    sealed = seal_cache(
        payload,
        secret=SECRET,
        now=NOW,
    )

    encoded, signature = sealed.split(".", 1)

    import base64
    import json

    raw = base64.urlsafe_b64decode(encoded)
    envelope = json.loads(raw)

    envelope["payload"]["license_status"] = "active"

    # Modify the encoded JSON without updating the signature.
    envelope["payload"]["license_id"] = "attacker-license"

    modified = base64.urlsafe_b64encode(
        json.dumps(
            envelope,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).decode()

    tampered = modified + "." + signature

    result = open_cache(
        tampered,
        secret=SECRET,
        now=NOW,
    )

    assert result.ok is False
    assert result.reason == "invalid_signature"


def test_wrong_secret_is_rejected():
    sealed = seal_cache(
        {"license_status": "active"},
        secret=SECRET,
        now=NOW,
    )

    result = open_cache(
        sealed,
        secret=b"wrong-secret",
        now=NOW,
    )

    assert result.ok is False
    assert result.reason == "invalid_signature"


def test_malformed_cache_fails_closed():
    result = open_cache(
        "not-a-cache",
        secret=SECRET,
        now=NOW,
    )

    assert result.ok is False
    assert result.payload is None


def test_future_cache_is_rejected():
    sealed = seal_cache(
        {"license_status": "active"},
        secret=SECRET,
        now=NOW + timedelta(minutes=10),
    )

    result = open_cache(
        sealed,
        secret=SECRET,
        now=NOW,
    )

    assert result.ok is False
    assert result.reason == "cache_from_future"


def test_rollback_limitation_is_explicit():
    old_cache = seal_cache(
        {
            "license_status": "active",
            "license_expires": "2026-08-20T00:00:00+00:00",
        },
        secret=SECRET,
        now=NOW,
    )

    later = NOW + timedelta(days=1)

    result = open_cache(
        old_cache,
        secret=SECRET,
        now=later,
    )

    # The signature remains valid because the cache really was issued
    # by the trusted issuer. Local-only storage cannot prove that it
    # has since been superseded.
    assert result.ok is True