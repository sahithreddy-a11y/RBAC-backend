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
        "license_status": "active",
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
    assert claims.license_status == "active"


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


def test_license_status_defaults_to_active():
    payload = {
        "sub": "user-123",
    }

    claims = parse_claims(payload)

    assert claims.license_status == "active"


def test_license_status_is_parsed():
    payload = {
        "sub": "user-123",
        "license_status": "revoked",
    }

    claims = parse_claims(payload)

    assert claims.license_status == "revoked"


def test_license_status_whitespace_is_stripped():
    payload = {
        "sub": "user-123",
        "license_status": " suspended ",
    }

    claims = parse_claims(payload)

    assert claims.license_status == "suspended"


def test_empty_license_status_defaults_to_active():
    payload = {
        "sub": "user-123",
        "license_status": "",
    }

    claims = parse_claims(payload)

    assert claims.license_status == "active"


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


def test_modules_invalid_integer_defaults_to_empty_list():
    payload = {
        "sub": "x",
        "modules": 5,
    }

    claims = parse_claims(payload)

    assert claims.modules == []


def test_modules_invalid_dict_defaults_to_empty_list():
    payload = {
        "sub": "x",
        "modules": {"a": 1},
    }

    claims = parse_claims(payload)

    assert claims.modules == []


def test_non_dict_payload_raises_error():
    with pytest.raises(ValueError, match="Invalid claims payload"):
        parse_claims("not-a-dict")


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
        license_status="active",
    )

    with pytest.raises(AttributeError):
        claims.role = "admin"


def test_sub_whitespace_is_stripped():
    payload = {
        "sub": "  user-123  ",
    }

    claims = parse_claims(payload)

    assert claims.sub == "user-123"


def test_non_string_email_becomes_none():
    payload = {
        "sub": "user-123",
        "email": 123,
    }

    claims = parse_claims(payload)

    assert claims.email is None


def test_non_string_org_id_becomes_none():
    payload = {
        "sub": "user-123",
        "org_id": {},
    }

    claims = parse_claims(payload)

    assert claims.org_id is None


def test_non_string_license_id_becomes_none():
    payload = {
        "sub": "user-123",
        "license_id": [],
    }

    claims = parse_claims(payload)

    assert claims.license_id is None



def test_license_status_is_parsed():
    payload = {
        "sub": "user-123",
        "license_status": "revoked",
    }

    claims = parse_claims(payload)

    assert claims.license_status == "revoked"


def test_missing_license_status_defaults_to_active():
    payload = {
        "sub": "user-123",
    }

    claims = parse_claims(payload)

    assert claims.license_status == "active"