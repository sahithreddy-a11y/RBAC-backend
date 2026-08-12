from datetime import datetime, timezone

import jwt

from backend.src.rbac.authorize import AuthorizationResult, authorize_launch


ISSUER = "https://issuer.example.com"
AUDIENCE = "biovaram-research"

PRIVATE_KEY = """-----BEGIN RSA PRIVATE KEY-----
MIIEowIBAAKCAQEA7
-----END RSA PRIVATE KEY-----"""


# The tests below use monkeypatching rather than depending on real
# cryptographic keys. This lets us test Task 11's composition rules:
# ordering, short-circuiting, reason propagation and clock handling.


def _verified_claims(
    *,
    sub="user-123",
    email="researcher@example.com",
    role="researcher",
    modules=None,
    license_expires=None,
):
    return {
        "sub": sub,
        "email": email,
        "role": role,
        "modules": modules if modules is not None else ["fcs"],
        "license_expires": license_expires,
    }


def test_successful_launch_returns_authorization_result(monkeypatch):
    calls = []

    class Verified:
        valid = True
        reason = "ok"
        claims = _verified_claims()

    def fake_verify(*args, **kwargs):
        calls.append("verify")
        return Verified()

    def fake_parse(payload):
        calls.append("parse")

        class Claims:
            email = "researcher@example.com"
            role = "researcher"
            modules = ["fcs"]
            license_expires = None

        return Claims()

    class License:
        valid = True
        reason = "perpetual"
        show_warning = False
        days_remaining = None

    def fake_license(*args):
        calls.append("license")
        return License()

    class Resolution:
        granted = ["fcs"]
        rejected = {}

    def fake_modules(*args):
        calls.append("modules")
        return Resolution()

    monkeypatch.setattr(
        "backend.src.rbac.authorize.verify_token",
        fake_verify,
    )
    monkeypatch.setattr(
        "backend.src.rbac.authorize.parse_claims",
        fake_parse,
    )
    monkeypatch.setattr(
        "backend.src.rbac.authorize.evaluate_license",
        fake_license,
    )
    monkeypatch.setattr(
        "backend.src.rbac.authorize.resolve_user_modules",
        fake_modules,
    )

    result = authorize_launch(
        "token",
        {"keys": []},
        issuer=ISSUER,
        audience=AUDIENCE,
        license_modules=["fcs"],
    )

    assert isinstance(result, AuthorizationResult)
    assert result.allowed is True
    assert result.modules == ["fcs"]
    assert result.reason == "ok"
    assert result.user_email == "researcher@example.com"
    assert result.role == "researcher"
    assert result.warning is None

    assert calls == [
        "verify",
        "parse",
        "license",
        "modules",
    ]


def test_verification_failure_short_circuits(monkeypatch):
    calls = []

    class Verified:
        valid = False
        reason = "bad_signature"
        claims = None

    def fake_verify(*args, **kwargs):
        calls.append("verify")
        return Verified()

    def should_not_parse(*args, **kwargs):
        calls.append("parse")
        raise AssertionError("parse must not run")

    def should_not_license(*args, **kwargs):
        calls.append("license")
        raise AssertionError("license must not run")

    def should_not_modules(*args, **kwargs):
        calls.append("modules")
        raise AssertionError("modules must not run")

    monkeypatch.setattr(
        "backend.src.rbac.authorize.verify_token",
        fake_verify,
    )
    monkeypatch.setattr(
        "backend.src.rbac.authorize.parse_claims",
        should_not_parse,
    )
    monkeypatch.setattr(
        "backend.src.rbac.authorize.evaluate_license",
        should_not_license,
    )
    monkeypatch.setattr(
        "backend.src.rbac.authorize.resolve_user_modules",
        should_not_modules,
    )

    result = authorize_launch(
        "bad-token",
        {"keys": []},
        issuer=ISSUER,
        audience=AUDIENCE,
        license_modules=["fcs"],
    )

    assert result.allowed is False
    assert result.modules == []
    assert result.reason == "verification:bad_signature"
    assert calls == ["verify"]


def test_claim_parsing_failure_short_circuits(monkeypatch):
    calls = []

    class Verified:
        valid = True
        reason = "ok"
        claims = {"sub": "user"}

    def fake_verify(*args, **kwargs):
        calls.append("verify")
        return Verified()

    def fake_parse(*args, **kwargs):
        calls.append("parse")
        raise ValueError("invalid claims")

    def should_not_license(*args, **kwargs):
        calls.append("license")
        raise AssertionError("license must not run")

    def should_not_modules(*args, **kwargs):
        calls.append("modules")
        raise AssertionError("modules must not run")

    monkeypatch.setattr(
        "backend.src.rbac.authorize.verify_token",
        fake_verify,
    )
    monkeypatch.setattr(
        "backend.src.rbac.authorize.parse_claims",
        fake_parse,
    )
    monkeypatch.setattr(
        "backend.src.rbac.authorize.evaluate_license",
        should_not_license,
    )
    monkeypatch.setattr(
        "backend.src.rbac.authorize.resolve_user_modules",
        should_not_modules,
    )

    result = authorize_launch(
        "token",
        {"keys": []},
        issuer=ISSUER,
        audience=AUDIENCE,
        license_modules=["fcs"],
    )

    assert result.allowed is False
    assert result.modules == []
    assert result.reason == "claims:invalid"
    assert calls == ["verify", "parse"]


def test_invalid_license_short_circuits_modules(monkeypatch):
    calls = []

    class Verified:
        valid = True
        reason = "ok"
        claims = _verified_claims()

    class Claims:
        email = "researcher@example.com"
        role = "researcher"
        modules = ["fcs"]
        license_expires = "2020-01-01"

    class License:
        valid = False
        reason = "expired"
        show_warning = False
        days_remaining = 0

    def fake_verify(*args, **kwargs):
        calls.append("verify")
        return Verified()

    def fake_parse(*args, **kwargs):
        calls.append("parse")
        return Claims()

    def fake_license(*args, **kwargs):
        calls.append("license")
        return License()

    def should_not_modules(*args, **kwargs):
        calls.append("modules")
        raise AssertionError("modules must not run")

    monkeypatch.setattr(
        "backend.src.rbac.authorize.verify_token",
        fake_verify,
    )
    monkeypatch.setattr(
        "backend.src.rbac.authorize.parse_claims",
        fake_parse,
    )
    monkeypatch.setattr(
        "backend.src.rbac.authorize.evaluate_license",
        fake_license,
    )
    monkeypatch.setattr(
        "backend.src.rbac.authorize.resolve_user_modules",
        should_not_modules,
    )

    result = authorize_launch(
        "token",
        {"keys": []},
        issuer=ISSUER,
        audience=AUDIENCE,
        license_modules=["fcs"],
    )

    assert result.allowed is False
    assert result.modules == []
    assert result.reason == "license:expired"
    assert result.user_email == "researcher@example.com"
    assert result.role == "researcher"

    assert calls == [
        "verify",
        "parse",
        "license",
    ]


def test_license_warning_is_returned(monkeypatch):
    class Verified:
        valid = True
        reason = "ok"
        claims = _verified_claims()

    class Claims:
        email = "researcher@example.com"
        role = "researcher"
        modules = ["fcs"]
        license_expires = "2026-08-20"

    class License:
        valid = True
        reason = "ok"
        show_warning = True
        days_remaining = 12

    class Resolution:
        granted = ["fcs"]
        rejected = {}

    monkeypatch.setattr(
        "backend.src.rbac.authorize.verify_token",
        lambda *args, **kwargs: Verified(),
    )
    monkeypatch.setattr(
        "backend.src.rbac.authorize.parse_claims",
        lambda *args, **kwargs: Claims(),
    )
    monkeypatch.setattr(
        "backend.src.rbac.authorize.evaluate_license",
        lambda *args, **kwargs: License(),
    )
    monkeypatch.setattr(
        "backend.src.rbac.authorize.resolve_user_modules",
        lambda *args, **kwargs: Resolution(),
    )

    result = authorize_launch(
        "token",
        {"keys": []},
        issuer=ISSUER,
        audience=AUDIENCE,
        license_modules=["fcs"],
    )

    assert result.allowed is True
    assert result.warning == "Licence expires in 12 days"


def test_module_resolution_trims_unlicensed_modules(monkeypatch):
    class Verified:
        valid = True
        reason = "ok"
        claims = _verified_claims()

    class Claims:
        email = "researcher@example.com"
        role = "researcher"
        modules = ["fcs", "nta"]

        license_expires = None

    class License:
        valid = True
        reason = "perpetual"
        show_warning = False
        days_remaining = None

    class Resolution:
        granted = ["fcs"]
        rejected = {"nta": "not_in_license"}

    monkeypatch.setattr(
        "backend.src.rbac.authorize.verify_token",
        lambda *args, **kwargs: Verified(),
    )
    monkeypatch.setattr(
        "backend.src.rbac.authorize.parse_claims",
        lambda *args, **kwargs: Claims(),
    )
    monkeypatch.setattr(
        "backend.src.rbac.authorize.evaluate_license",
        lambda *args, **kwargs: License(),
    )
    monkeypatch.setattr(
        "backend.src.rbac.authorize.resolve_user_modules",
        lambda *args, **kwargs: Resolution(),
    )

    result = authorize_launch(
        "token",
        {"keys": []},
        issuer=ISSUER,
        audience=AUDIENCE,
        license_modules=["fcs"],
    )

    assert result.allowed is True
    assert result.modules == ["fcs"]


def test_one_normalized_clock_is_passed_to_license(monkeypatch):
    captured = []

    expected_now = datetime(
        2026,
        8,
        12,
        10,
        30,
        tzinfo=timezone.utc,
    )

    class Verified:
        valid = True
        reason = "ok"
        claims = _verified_claims()

    class Claims:
        email = "researcher@example.com"
        role = "researcher"
        modules = ["fcs"]
        license_expires = None

    class License:
        valid = True
        reason = "perpetual"
        show_warning = False
        days_remaining = None

    class Resolution:
        granted = ["fcs"]
        rejected = {}

    def fake_license(status, expiry, now):
        captured.append(now)
        return License()

    monkeypatch.setattr(
        "backend.src.rbac.authorize.verify_token",
        lambda *args, **kwargs: Verified(),
    )
    monkeypatch.setattr(
        "backend.src.rbac.authorize.parse_claims",
        lambda *args, **kwargs: Claims(),
    )
    monkeypatch.setattr(
        "backend.src.rbac.authorize.evaluate_license",
        fake_license,
    )
    monkeypatch.setattr(
        "backend.src.rbac.authorize.resolve_user_modules",
        lambda *args, **kwargs: Resolution(),
    )

    result = authorize_launch(
        "token",
        {"keys": []},
        issuer=ISSUER,
        audience=AUDIENCE,
        license_modules=["fcs"],
        now=expected_now,
    )

    assert result.allowed is True
    assert captured == [expected_now]


def test_naive_datetime_is_treated_as_utc(monkeypatch):
    captured = []

    class Verified:
        valid = True
        reason = "ok"
        claims = _verified_claims()

    class Claims:
        email = None
        role = "researcher"
        modules = ["fcs"]
        license_expires = None

    class License:
        valid = True
        reason = "perpetual"
        show_warning = False
        days_remaining = None

    class Resolution:
        granted = ["fcs"]
        rejected = {}

    def fake_license(status, expiry, now):
        captured.append(now)
        return License()

    monkeypatch.setattr(
        "backend.src.rbac.authorize.verify_token",
        lambda *args, **kwargs: Verified(),
    )
    monkeypatch.setattr(
        "backend.src.rbac.authorize.parse_claims",
        lambda *args, **kwargs: Claims(),
    )
    monkeypatch.setattr(
        "backend.src.rbac.authorize.evaluate_license",
        fake_license,
    )
    monkeypatch.setattr(
        "backend.src.rbac.authorize.resolve_user_modules",
        lambda *args, **kwargs: Resolution(),
    )

    naive = datetime(2026, 8, 12, 10, 30)

    result = authorize_launch(
        "token",
        {"keys": []},
        issuer=ISSUER,
        audience=AUDIENCE,
        license_modules=["fcs"],
        now=naive,
    )

    assert result.allowed is True
    assert captured[0] == naive.replace(tzinfo=timezone.utc)


def test_invalid_now_fails_safely():
    result = authorize_launch(
        "token",
        {"keys": []},
        issuer=ISSUER,
        audience=AUDIENCE,
        license_modules=["fcs"],
        now="not-a-datetime",
    )

    assert result.allowed is False
    assert result.modules == []
    assert result.reason == "authorization:invalid_now"


def test_invalid_top_level_inputs_fail_without_pipeline():
    result = authorize_launch(
        "",
        {"keys": []},
        issuer=ISSUER,
        audience=AUDIENCE,
        license_modules=["fcs"],
    )

    assert result.allowed is False
    assert result.modules == []
    assert result.reason == "verification:malformed"


def test_result_does_not_expose_modules_when_denied(monkeypatch):
    class Verified:
        valid = False
        reason = "expired"
        claims = None

    monkeypatch.setattr(
        "backend.src.rbac.authorize.verify_token",
        lambda *args, **kwargs: Verified(),
    )

    result = authorize_launch(
        "token",
        {"keys": []},
        issuer=ISSUER,
        audience=AUDIENCE,
        license_modules=["fcs", "nta"],
    )

    assert result.allowed is False
    assert result.modules == []


def test_result_is_immutable(monkeypatch):
    class Verified:
        valid = True
        reason = "ok"
        claims = _verified_claims()

    class Claims:
        email = "user@example.com"
        role = "researcher"
        modules = ["fcs"]
        license_expires = None

    class License:
        valid = True
        reason = "perpetual"
        show_warning = False
        days_remaining = None

    class Resolution:
        granted = ["fcs"]
        rejected = {}

    monkeypatch.setattr(
        "backend.src.rbac.authorize.verify_token",
        lambda *args, **kwargs: Verified(),
    )
    monkeypatch.setattr(
        "backend.src.rbac.authorize.parse_claims",
        lambda *args, **kwargs: Claims(),
    )
    monkeypatch.setattr(
        "backend.src.rbac.authorize.evaluate_license",
        lambda *args, **kwargs: License(),
    )
    monkeypatch.setattr(
        "backend.src.rbac.authorize.resolve_user_modules",
        lambda *args, **kwargs: Resolution(),
    )

    result = authorize_launch(
        "token",
        {"keys": []},
        issuer=ISSUER,
        audience=AUDIENCE,
        license_modules=["fcs"],
    )

    try:
        result.allowed = False
        assert False, "AuthorizationResult should be immutable"
    except AttributeError:
        pass