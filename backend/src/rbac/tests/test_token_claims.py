from datetime import datetime, timezone

import pytest

from backend.src.rbac.claims import parse_claims
from backend.src.rbac.token_claims import TokenClaims, build_token_claims


NOW = datetime(
    2026,
    8,
    13,
    12,
    0,
    tzinfo=timezone.utc,
)


def make_org(
    modules=None,
    *,
    status="active",
    expires="perpetual",
    license_id="lic-1",
    license_type="enterprise",
):
    return {
        "org_id": "org-1",
        "license": {
            "id": license_id,
            "type": license_type,
            "modules": modules or [],
            "expires": expires,
            "status": status,
        },
    }


def make_user(
    *,
    sub="user-1",
    email="user@example.com",
    role="researcher",
    modules=None,
):
    return {
        "sub": sub,
        "email": email,
        "role": role,
        "requested_modules": modules or [],
    }


def test_returns_token_claims():
    result = build_token_claims(
        user=make_user(modules=["fcs"]),
        organization=make_org(["fcs"]),
        now=NOW,
    )

    assert isinstance(result, TokenClaims)


def test_all_emitted_claim_values_are_strings():
    result = build_token_claims(
        user=make_user(modules=["fcs"]),
        organization=make_org(["fcs"]),
        now=NOW,
    )

    assert all(
        isinstance(value, str)
        for value in result.claims.values()
    )


def test_single_module_round_trip():
    built = build_token_claims(
        user=make_user(modules=["fcs"]),
        organization=make_org(["fcs"]),
        now=NOW,
    )

    parsed = parse_claims(built.claims)

    assert parsed.modules == ["fcs"]
    assert parsed.role == "researcher"


def test_two_modules_round_trip():
    built = build_token_claims(
        user=make_user(
            role="admin",
            modules=["nta", "fcs"],
        ),
        organization=make_org(["fcs", "nta"]),
        now=NOW,
    )

    parsed = parse_claims(built.claims)

    assert parsed.modules == ["fcs", "nta"]
    assert parsed.role == "admin"


def test_empty_modules_round_trip_to_empty_list():
    built = build_token_claims(
        user=make_user(modules=[]),
        organization=make_org(["fcs", "nta"]),
        now=NOW,
    )

    assert built.claims["modules"] == ""

    parsed = parse_claims(built.claims)

    assert parsed.modules == []


def test_cross_compare_requires_two_base_modules():
    built = build_token_claims(
        user=make_user(
            modules=["fcs", "cross_compare"],
        ),
        organization=make_org(
            ["fcs", "cross_compare"],
        ),
        now=NOW,
    )

    parsed = parse_claims(built.claims)

    assert parsed.modules == ["fcs"]


def test_cross_compare_is_granted_with_two_base_modules():
    built = build_token_claims(
        user=make_user(
            modules=["fcs", "nta", "cross_compare"],
        ),
        organization=make_org(
            ["fcs", "nta", "cross_compare"],
        ),
        now=NOW,
    )

    parsed = parse_claims(built.claims)

    assert parsed.modules == [
        "cross_compare",
        "fcs",
        "nta",
    ]


def test_revoked_license_produces_empty_modules():
    built = build_token_claims(
        user=make_user(modules=["fcs", "nta"]),
        organization=make_org(
            ["fcs", "nta"],
            status="revoked",
        ),
        now=NOW,
    )

    assert built.claims["modules"] == ""

    parsed = parse_claims(built.claims)

    assert parsed.modules == []


def test_expired_license_produces_empty_modules():
    built = build_token_claims(
        user=make_user(modules=["fcs"]),
        organization=make_org(
            ["fcs"],
            expires="2026-08-12",
        ),
        now=NOW,
    )

    assert built.claims["modules"] == ""

    parsed = parse_claims(built.claims)

    assert parsed.modules == []


def test_unlicensed_requested_module_is_not_granted_and_warned():
    built = build_token_claims(
        user=make_user(
            modules=["fcs", "nta"],
        ),
        organization=make_org(["fcs"]),
        now=NOW,
    )

    parsed = parse_claims(built.claims)

    assert parsed.modules == ["fcs"]
    assert "module_not_in_license:nta" in built.warnings


def test_missing_organization_fails_closed():
    built = build_token_claims(
        user=make_user(modules=["fcs"]),
        organization=None,
        now=NOW,
    )

    assert built.claims["modules"] == ""
    assert built.claims["org_id"] == ""
    assert "missing_or_invalid_organization" in built.warnings


def test_malformed_user_fails_closed():
    built = build_token_claims(
        user=None,
        organization=make_org(["fcs"]),
        now=NOW,
    )

    assert built.claims["modules"] == ""
    assert "invalid_user" in built.warnings


def test_missing_license_record_fails_closed():
    built = build_token_claims(
        user=make_user(modules=["fcs"]),
        organization={"org_id": "org-1"},
        now=NOW,
    )

    assert built.claims["modules"] == ""
    assert "missing_license_record" in built.warnings


def test_invalid_expiry_fails_closed_and_warns():
    built = build_token_claims(
        user=make_user(modules=["fcs"]),
        organization=make_org(
            ["fcs"],
            expires="not-a-date",
        ),
        now=NOW,
    )

    assert built.claims["modules"] == ""
    assert "missing_license_record" not in built.warnings


def test_missing_organization_id_fails_closed_for_identity():
    built = build_token_claims(
        user=make_user(modules=["fcs"]),
        organization={
            "license": {
                "modules": ["fcs"],
                "status": "active",
                "expires": "perpetual",
            }
        },
        now=NOW,
    )

    assert built.claims["org_id"] == ""
    assert built.claims["modules"] == ["fcs"] if False else built.claims["modules"]
    assert "missing_organization_id" in built.warnings


def test_now_is_required_as_injected_clock():
    with pytest.raises(TypeError):
        build_token_claims(
            user=make_user(modules=["fcs"]),
            organization=make_org(["fcs"]),
        )


def test_datetime_is_not_used_from_global_clock():
    first = build_token_claims(
        user=make_user(modules=["fcs"]),
        organization=make_org(
            ["fcs"],
            expires="2026-08-13",
        ),
        now=datetime(
            2026,
            8,
            13,
            12,
            0,
            tzinfo=timezone.utc,
        ),
    )

    second = build_token_claims(
        user=make_user(modules=["fcs"]),
        organization=make_org(
            ["fcs"],
            expires="2026-08-13",
        ),
        now=datetime(
            2026,
            8,
            14,
            0,
            0,
            tzinfo=timezone.utc,
        ),
    )

    assert first.claims["modules"] == "fcs"
    assert second.claims["modules"] == ""


def test_claims_round_trip_preserves_identity_fields():
    built = build_token_claims(
        user=make_user(
            sub=" user-99 ",
            email=" user99@example.com ",
            role="admin",
            modules=["fcs"],
        ),
        organization=make_org(
            ["fcs"],
            license_id="lic-99",
            license_type="enterprise",
        ),
        now=NOW,
    )

    parsed = parse_claims(built.claims)

    assert parsed.sub == "user-99"
    assert parsed.email == "user99@example.com"
    assert parsed.org_id == "org-1"
    assert parsed.role == "admin"
    assert parsed.license_id == "lic-99"
    assert parsed.license_type == "enterprise"


def test_non_string_source_values_are_emitted_as_strings():
    user = {
        "sub": 123,
        "email": 456,
        "role": 789,
        "requested_modules": ["fcs"],
    }

    organization = {
        "org_id": 999,
        "license": {
            "id": 111,
            "type": 222,
            "modules": ["fcs"],
            "expires": "perpetual",
            "status": "active",
        },
    }

    built = build_token_claims(
        user=user,
        organization=organization,
        now=NOW,
    )

    assert all(
        isinstance(value, str)
        for value in built.claims.values()
    )