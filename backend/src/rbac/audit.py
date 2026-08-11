from datetime import datetime, timezone
from uuid import uuid4


EVENT_TYPES = frozenset({
    "LOGIN",
    "LOGOUT",
    "MODULE_LAUNCH",
    "LICENSE_ACTIVATE",
    "LICENSE_REVOKE",
    "USER_INVITE",
    "USER_DEACTIVATE",
    "MODULE_ACCESS_CHANGE",
    "TOKEN_REFRESH_FAILED",
})


SENSITIVE_KEYS = frozenset({
    "password",
    "passwd",
    "secret",
    "token",
    "access_token",
    "refresh_token",
    "authorization",
    "api_key",
    "apikey",
    "client_secret",
    "private_key",
})


def _redact_metadata(value):
    """Return a redacted copy of metadata without mutating the input."""
    if isinstance(value, dict):
        return {
            key: (
                "[REDACTED]"
                if isinstance(key, str) and key.lower() in SENSITIVE_KEYS
                else _redact_metadata(item)
            )
            for key, item in value.items()
        }

    if isinstance(value, list):
        return [_redact_metadata(item) for item in value]

    if isinstance(value, tuple):
        return tuple(_redact_metadata(item) for item in value)

    return value


def build_audit_event(
    event_type: str,
    *,
    user_id: str,
    org_id: str | None = None,
    license_id: str | None = None,
    module_id: str | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
    success: bool = True,
    metadata: dict | None = None,
    now: datetime | None = None,
) -> dict:
    """Build a well-formed, safely redacted audit event."""

    if event_type not in EVENT_TYPES:
        raise ValueError(f"Unknown event type: {event_type}")

    if now is None:
        now = datetime.now(timezone.utc)
    elif now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    else:
        now = now.astimezone(timezone.utc)

    return {
        "event_id": str(uuid4()),
        "event_type": event_type,
        "timestamp": now.isoformat(),
        "user_id": user_id,
        "org_id": org_id,
        "license_id": license_id,
        "module_id": module_id,
        "ip_address": ip_address,
        "user_agent": user_agent,
        "success": success,
        "metadata": _redact_metadata(metadata) if metadata is not None else {},
    }