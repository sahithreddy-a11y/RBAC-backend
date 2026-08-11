import pytest

from backend.src.rbac.claims import Claims, parse_claims


def test_parse_claims_with_all_fields():
    payload = {
        "sub": "user-123",
        "email": "user@example.com",
        "org_id": "org-456",
        "role": "admin",
        "modules": "research, analytics, reports",
        "license_id": "lic-789",
        "license_type": "enterprise",
        "license_expires": "2026-12-31",
    }

    claims = parse_claims(payload)

    assert claims.sub == "user-123"
    assert claims.email == "user@example.com"
    assert claims.org_id == "org-456"
    assert claims.role == "admin"
    assert claims.modules == ["research", "analytics", "reports"]
    assert claims.license_id == "lic-789"
    assert claims.license_type == "enterprise"
    assert claims.license_expires == "2026-12-31"


def test_modules_can_be_a_list():
    payload = {
        "sub": "user-123",
        "modules": ["research", "analytics"],
    }

    claims = parse_claims(payload)

    assert claims.modules == ["research", "analytics"]


def test_modules_strip_whitespace_and_empty_values():
    payload = {
        "sub": "user-123",
        "modules": "research, , analytics, ,reports ",
    }

    claims = parse_claims(payload)

    assert claims.modules == ["research", "analytics", "reports"]


def test_default_role_is_researcher():
    payload = {
        "sub": "user-123",
    }

    claims = parse_claims(payload)

    assert claims.role == "researcher"


def test_missing_modules_defaults_to_empty_list():
    payload = {
        "sub": "user-123",
    }

    claims = parse_claims(payload)

    assert claims.modules == []


def test_optional_claims_default_to_none():
    payload = {
        "sub": "user-123",
    }

    claims = parse_claims(payload)

    assert claims.email is None
    assert claims.org_id is None
    assert claims.license_id is None
    assert claims.license_type is None
    assert claims.license_expires is None


def test_empty_email_becomes_none():
    payload = {
        "sub": "user-123",
        "email": "",
    }

    claims = parse_claims(payload)

    assert claims.email is None


def test_missing_sub_raises_error():
    payload = {
        "email": "user@example.com",
    }

    with pytest.raises(ValueError, match="Missing required claim: sub"):
        parse_claims(payload)


def test_claims_are_immutable():
    claims = Claims(
        sub="user-123",
        email=None,
        org_id=None,
        role="researcher",
        modules=[],
        license_id=None,
        license_type=None,
        license_expires=None,
    )

    with pytest.raises(AttributeError):
        claims.role = "admin"