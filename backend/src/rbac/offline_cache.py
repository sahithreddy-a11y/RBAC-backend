from __future__ import annotations

import base64
import hashlib
import hmac
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


@dataclass(frozen=True)
class CacheOpenResult:
    payload: dict[str, Any] | None
    ok: bool
    reason: str


def _canonical_json(value: dict[str, Any]) -> bytes:
    """Serialize deterministically so signing and verification agree."""
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def _timestamp(value: datetime) -> str:
    """Normalize timestamps to UTC ISO-8601."""
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)

    return value.astimezone(timezone.utc).isoformat()


def _sign(data: bytes, secret: bytes) -> bytes:
    return hmac.new(
        secret,
        data,
        hashlib.sha256,
    ).digest()


def seal_cache(
    payload: dict,
    *,
    secret: bytes,
    now: datetime,
) -> str:
    """
    Serialize and HMAC-sign an offline licence cache.

    The issued_at timestamp is included inside the signed envelope.
    """
    if not isinstance(payload, dict):
        raise TypeError("payload must be a dict")

    if not isinstance(secret, bytes) or not secret:
        raise ValueError("secret must be non-empty bytes")

    envelope = {
        "version": 1,
        "issued_at": _timestamp(now),
        "payload": payload,
    }

    encoded = _canonical_json(envelope)
    signature = _sign(encoded, secret)

    # URL-safe representation suitable for storing in a file/string.
    return (
        base64.urlsafe_b64encode(encoded).decode("ascii")
        + "."
        + base64.urlsafe_b64encode(signature).decode("ascii")
    )


def open_cache(
    sealed: str,
    *,
    secret: bytes,
    now: datetime,
) -> CacheOpenResult:
    """
    Verify and open an offline licence cache.

    Fails closed for malformed input, invalid signatures, future-issued
    caches, and invalid timestamps.

    Rollback limitation:
    a previously valid sealed cache can still be copied back by a user
    who controls the machine. Without trusted external state, this
    function cannot know that the older cache was previously superseded.
    """
    if not isinstance(sealed, str) or not sealed:
        return CacheOpenResult(
            payload=None,
            ok=False,
            reason="malformed_cache",
        )

    if not isinstance(secret, bytes) or not secret:
        return CacheOpenResult(
            payload=None,
            ok=False,
            reason="invalid_secret",
        )

    try:
        encoded_part, signature_part = sealed.split(".", 1)

        encoded = base64.urlsafe_b64decode(
            encoded_part.encode("ascii")
        )
        actual_signature = base64.urlsafe_b64decode(
            signature_part.encode("ascii")
        )
    except (ValueError, UnicodeError, base64.binascii.Error):
        return CacheOpenResult(
            payload=None,
            ok=False,
            reason="malformed_cache",
        )

    expected_signature = _sign(encoded, secret)

    # Constant-time comparison is required for MAC verification.
    if not hmac.compare_digest(expected_signature, actual_signature):
        return CacheOpenResult(
            payload=None,
            ok=False,
            reason="invalid_signature",
        )

    try:
        envelope = json.loads(encoded.decode("utf-8"))

        if not isinstance(envelope, dict):
            raise ValueError

        if envelope.get("version") != 1:
            return CacheOpenResult(
                payload=None,
                ok=False,
                reason="unsupported_version",
            )

        issued_at_raw = envelope["issued_at"]
        payload = envelope["payload"]

        if not isinstance(issued_at_raw, str):
            raise ValueError

        if not isinstance(payload, dict):
            raise ValueError

        issued_at = datetime.fromisoformat(issued_at_raw)

        if issued_at.tzinfo is None:
            issued_at = issued_at.replace(tzinfo=timezone.utc)

        issued_at = issued_at.astimezone(timezone.utc)

        current_time = now
        if current_time.tzinfo is None:
            current_time = current_time.replace(tzinfo=timezone.utc)

        current_time = current_time.astimezone(timezone.utc)

    except (KeyError, TypeError, ValueError, UnicodeError, json.JSONDecodeError):
        return CacheOpenResult(
            payload=None,
            ok=False,
            reason="malformed_cache",
        )

    # A cache claiming to have been issued in the future is suspicious.
    # Allow only a small clock-skew window.
    if issued_at > current_time:
        return CacheOpenResult(
            payload=None,
            ok=False,
            reason="cache_from_future",
        )

    return CacheOpenResult(
        payload=payload,
        ok=True,
        reason="valid",
    )