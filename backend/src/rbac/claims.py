"""
Token claims parsing only.

This module parses claims from a token payload; it does not verify the token.
It does not check a signature, issuer, or expiry. Calling this on an untrusted
token tells you what that token claims, not what is true. Signature
verification happens before this function is called.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Claims:
    sub: str
    email: str | None
    org_id: str | None
    role: str
    modules: list[str]
    license_id: str | None
    license_type: str | None
    license_expires: str | None


def _optional_string(value) -> str | None:
    if value is None:
        return None

    if isinstance(value, str):
        value = value.strip()
        return value or None

    return value


def _parse_modules(value) -> list[str]:
    if value is None:
        return []

    if isinstance(value, str):
        value = value.split(",")

    if not isinstance(value, (list, tuple)):
        return []

    return [
        item.strip()
        for item in value
        if isinstance(item, str) and item.strip()
    ]


def parse_claims(payload: dict) -> Claims:
    if not isinstance(payload, dict):
        raise ValueError("Invalid claims payload")

    sub = payload.get("sub")

    if not isinstance(sub, str) or not sub.strip():
        raise ValueError("Missing required claim: sub")

    return Claims(
        sub=sub,
        email=_optional_string(payload.get("email")),
        org_id=_optional_string(payload.get("org_id")),
        role=_optional_string(payload.get("role")) or "researcher",
        modules=_parse_modules(payload.get("modules")),
        license_id=_optional_string(payload.get("license_id")),
        license_type=_optional_string(payload.get("license_type")),
        license_expires=_optional_string(payload.get("license_expires")),
    )