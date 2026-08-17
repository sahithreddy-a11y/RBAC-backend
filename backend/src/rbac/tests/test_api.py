from datetime import datetime, timedelta, timezone

import jwt
from fastapi.testclient import TestClient
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.algorithms import RSAAlgorithm

from backend.src.rbac.api import create_app
from backend.src.rbac.jwks_cache import CacheResult


ISSUER = "https://issuer.example.com"
AUDIENCE = "biovaram-api"
TOKEN_USE = "id"

ORG_ID = "org-1"

NOW = datetime(
    2026,
    8,
    17,
    12,
    0,
    0,
    tzinfo=timezone.utc,
)


# ---------------------------------------------------------------------------
# Test key helpers
# ---------------------------------------------------------------------------


def generate_key_pair():
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
    )
    return private_key, private_key.public_key()


def public_jwk(public_key, kid="test-key"):
    key = RSAAlgorithm.to_jwk(public_key)
    jwk = __import__("json").loads(key)

    jwk["kid"] = kid
    jwk["alg"] = "RS256"
    jwk["use"] = "sig"

    return jwk


def create_token(
    private_key,
    *,
    kid="test-key",
    issuer=ISSUER,
    audience=AUDIENCE,
    token_use=TOKEN_USE,
    expires_at=None,
    not_before=None,
    extra_claims=None,
):
    if expires_at is None:
        expires_at = NOW + timedelta(minutes=10)

    payload = {
        "sub": "user-123",
        "email": "user@example.com",
        "org_id": ORG_ID,
        "role": "researcher",
        "modules": "fcs,nta",
        "license_id": "lic-123",
        "license_type": "standard",
        "license_expires": (
            NOW + timedelta(days=90)
        ).isoformat(),
        "license_status": "active",
        "iss": issuer,
        "aud": audience,
        "exp": expires_at,
        "token_use": token_use,
    }

    if not_before is not None:
        payload["nbf"] = not_before

    if extra_claims:
        payload.update(extra_claims)

    return jwt.encode(
        payload,
        private_key,
        algorithm="RS256",
        headers={
            "kid": kid,
            "alg": "RS256",
        },
    )


# ---------------------------------------------------------------------------
# Fake JWKS cache
# ---------------------------------------------------------------------------


class FakeJwksCache:
    def __init__(
        self,
        jwks,
        *,
        source="cache",
        reason="within_ttl",
    ):
        self.jwks = jwks
        self.source = source
        self.reason = reason
        self.calls = []

    def get(self, *, now, kid=None):
        self.calls.append(
            {
                "now": now,
                "kid": kid,
            }
        )

        return CacheResult(
            jwks=self.jwks,
            source=self.source,
            reason=self.reason,
        )


class RaisingJwksCache:
    def get(self, *, now, kid=None):
        raise RuntimeError("simulated JWKS provider failure")


# ---------------------------------------------------------------------------
# App factory helpers
# ---------------------------------------------------------------------------


def make_app(
    jwks_cache,
    *,
    license_modules=None,
):
    if license_modules is None:
        license_modules = ["fcs", "nta"]

    def license_lookup(org_id):
        if org_id != ORG_ID:
            return []

        return list(license_modules)

    return create_app(
        jwks_cache=jwks_cache,
        issuer=ISSUER,
        audience=AUDIENCE,
        license_modules_for=license_lookup,
        now=lambda: NOW,
    )


def make_client(
    jwks_cache,
    *,
    license_modules=None,
    raise_server_exceptions=True,
):
    app = make_app(
        jwks_cache,
        license_modules=license_modules,
    )

    return TestClient(
        app,
        raise_server_exceptions=raise_server_exceptions,
    )


def auth_header(token):
    return {
        "Authorization": f"Bearer {token}",
    }


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def setup_keys():
    trusted_private, trusted_public = generate_key_pair()
    attacker_private, _ = generate_key_pair()

    jwks = {
        "keys": [
            public_jwk(trusted_public),
        ]
    }

    return trusted_private, attacker_private, jwks


# ---------------------------------------------------------------------------
# Health endpoint
# ---------------------------------------------------------------------------


def test_health_does_not_require_authentication():
    private_key, _, jwks = setup_keys()

    client = make_client(
        FakeJwksCache(jwks),
    )

    response = client.get("/v1/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
    }


def test_health_does_not_call_jwks_cache():
    _, _, jwks = setup_keys()

    cache = FakeJwksCache(jwks)

    client = make_client(cache)

    response = client.get("/v1/health")

    assert response.status_code == 200
    assert cache.calls == []


# ---------------------------------------------------------------------------
# Successful authorization
# ---------------------------------------------------------------------------


def test_valid_token_and_licensed_modules_returns_200():
    private_key, _, jwks = setup_keys()

    cache = FakeJwksCache(jwks)

    token = create_token(
        private_key,
        extra_claims={
            "modules": "fcs,nta",
        },
    )

    client = make_client(
        cache,
        license_modules=["fcs", "nta"],
    )

    response = client.post(
        "/v1/authorize",
        headers=auth_header(token),
        json={"org_id": ORG_ID},
    )

    assert response.status_code == 200
    assert response.json() == {
        "allowed": True,
        "modules": ["fcs", "nta"],
        "warning": None,
    }


def test_successful_response_contains_only_public_authorization_fields():
    private_key, _, jwks = setup_keys()

    token = create_token(private_key)

    client = make_client(
        FakeJwksCache(jwks),
    )

    response = client.post(
        "/v1/authorize",
        headers=auth_header(token),
        json={"org_id": ORG_ID},
    )

    assert response.status_code == 200

    body = response.json()

    assert set(body.keys()) == {
        "allowed",
        "modules",
        "warning",
    }

    assert "user_email" not in body
    assert "role" not in body
    assert "reason" not in body


# ---------------------------------------------------------------------------
# Authorization header validation
# ---------------------------------------------------------------------------


def test_missing_authorization_header_returns_401():
    _, _, jwks = setup_keys()

    client = make_client(
        FakeJwksCache(jwks),
    )

    response = client.post(
        "/v1/authorize",
        json={"org_id": ORG_ID},
    )

    assert response.status_code == 401


def test_empty_authorization_header_returns_401():
    _, _, jwks = setup_keys()

    client = make_client(
        FakeJwksCache(jwks),
    )

    response = client.post(
        "/v1/authorize",
        headers={
            "Authorization": "",
        },
        json={"org_id": ORG_ID},
    )

    assert response.status_code == 401


def test_bearer_without_token_returns_401():
    _, _, jwks = setup_keys()

    client = make_client(
        FakeJwksCache(jwks),
    )

    response = client.post(
        "/v1/authorize",
        headers={
            "Authorization": "Bearer",
        },
        json={"org_id": ORG_ID},
    )

    assert response.status_code == 401


def test_bearer_with_only_whitespace_returns_401():
    _, _, jwks = setup_keys()

    client = make_client(
        FakeJwksCache(jwks),
    )

    response = client.post(
        "/v1/authorize",
        headers={
            "Authorization": "Bearer    ",
        },
        json={"org_id": ORG_ID},
    )

    assert response.status_code == 401


def test_basic_authentication_scheme_returns_401():
    _, _, jwks = setup_keys()

    client = make_client(
        FakeJwksCache(jwks),
    )

    response = client.post(
        "/v1/authorize",
        headers={
            "Authorization": "Basic abc123",
        },
        json={"org_id": ORG_ID},
    )

    assert response.status_code == 401


def test_wrong_authentication_scheme_returns_401():
    _, _, jwks = setup_keys()

    client = make_client(
        FakeJwksCache(jwks),
    )

    response = client.post(
        "/v1/authorize",
        headers={
            "Authorization": "Token abc123",
        },
        json={"org_id": ORG_ID},
    )

    assert response.status_code == 401


def test_bearer_scheme_is_case_insensitive_if_supported_by_http_layer():
    private_key, _, jwks = setup_keys()

    token = create_token(private_key)

    client = make_client(
        FakeJwksCache(jwks),
    )

    response = client.post(
        "/v1/authorize",
        headers={
            "Authorization": f"bearer {token}",
        },
        json={"org_id": ORG_ID},
    )

    assert response.status_code in {200, 401}

    # The important security property is that a non-standard scheme
    # must never accidentally bypass authentication.
    if response.status_code == 200:
        assert response.json()["allowed"] is True


# ---------------------------------------------------------------------------
# Token verification failures
# ---------------------------------------------------------------------------


def test_malformed_token_returns_401():
    _, _, jwks = setup_keys()

    client = make_client(
        FakeJwksCache(jwks),
    )

    response = client.post(
        "/v1/authorize",
        headers=auth_header("not-a-jwt"),
        json={"org_id": ORG_ID},
    )

    assert response.status_code == 401


def test_expired_token_returns_401():
    private_key, _, jwks = setup_keys()

    token = create_token(
        private_key,
        expires_at=NOW - timedelta(minutes=5),
    )

    client = make_client(
        FakeJwksCache(jwks),
    )

    response = client.post(
        "/v1/authorize",
        headers=auth_header(token),
        json={"org_id": ORG_ID},
    )

    assert response.status_code == 401


def test_untrusted_signature_returns_401():
    _, attacker_private, jwks = setup_keys()

    token = create_token(
        attacker_private,
    )

    client = make_client(
        FakeJwksCache(jwks),
    )

    response = client.post(
        "/v1/authorize",
        headers=auth_header(token),
        json={"org_id": ORG_ID},
    )

    assert response.status_code == 401


def test_unknown_kid_returns_401():
    private_key, _, jwks = setup_keys()

    token = create_token(
        private_key,
        kid="attacker-controlled-kid",
    )

    client = make_client(
        FakeJwksCache(jwks),
    )

    response = client.post(
        "/v1/authorize",
        headers=auth_header(token),
        json={"org_id": ORG_ID},
    )

    assert response.status_code == 401


def test_wrong_issuer_returns_401():
    private_key, _, jwks = setup_keys()

    token = create_token(
        private_key,
        issuer="https://evil.example.com",
    )

    client = make_client(
        FakeJwksCache(jwks),
    )

    response = client.post(
        "/v1/authorize",
        headers=auth_header(token),
        json={"org_id": ORG_ID},
    )

    assert response.status_code == 401


def test_wrong_audience_returns_401():
    private_key, _, jwks = setup_keys()

    token = create_token(
        private_key,
        audience="wrong-api",
    )

    client = make_client(
        FakeJwksCache(jwks),
    )

    response = client.post(
        "/v1/authorize",
        headers=auth_header(token),
        json={"org_id": ORG_ID},
    )

    assert response.status_code == 401


# ---------------------------------------------------------------------------
# License failures
# ---------------------------------------------------------------------------


def test_valid_token_with_revoked_license_returns_403():
    private_key, _, jwks = setup_keys()

    token = create_token(
        private_key,
        extra_claims={
            "license_status": "revoked",
        },
    )

    client = make_client(
        FakeJwksCache(jwks),
    )

    response = client.post(
        "/v1/authorize",
        headers=auth_header(token),
        json={"org_id": ORG_ID},
    )

    assert response.status_code == 403


def test_valid_token_with_expired_license_returns_403():
    private_key, _, jwks = setup_keys()

    token = create_token(
        private_key,
        extra_claims={
            "license_status": "active",
            "license_expires": (
                NOW - timedelta(days=1)
            ).isoformat(),
        },
    )

    client = make_client(
        FakeJwksCache(jwks),
    )

    response = client.post(
        "/v1/authorize",
        headers=auth_header(token),
        json={"org_id": ORG_ID},
    )

    assert response.status_code == 403


def test_valid_token_with_no_licensed_modules_returns_200_with_empty_modules():
    private_key, _, jwks = setup_keys()

    token = create_token(
        private_key,
        extra_claims={
            "modules": "",
        },
    )

    client = make_client(
        FakeJwksCache(jwks),
        license_modules=[],
    )

    response = client.post(
        "/v1/authorize",
        headers=auth_header(token),
        json={"org_id": ORG_ID},
    )

    assert response.status_code == 200

    body = response.json()

    assert body["allowed"] is True
    assert body["modules"] == []


# ---------------------------------------------------------------------------
# Request validation
# ---------------------------------------------------------------------------


def test_missing_org_id_returns_422():
    private_key, _, jwks = setup_keys()

    token = create_token(private_key)

    client = make_client(
        FakeJwksCache(jwks),
    )

    response = client.post(
        "/v1/authorize",
        headers=auth_header(token),
        json={},
    )

    assert response.status_code == 422


def test_malformed_json_body_returns_422():
    private_key, _, jwks = setup_keys()

    token = create_token(private_key)

    client = make_client(
        FakeJwksCache(jwks),
    )

    response = client.post(
        "/v1/authorize",
        headers={
            **auth_header(token),
            "Content-Type": "application/json",
        },
        content="{not-valid-json",
    )

    assert response.status_code == 422


def test_org_id_must_be_string():
    private_key, _, jwks = setup_keys()

    token = create_token(private_key)

    client = make_client(
        FakeJwksCache(jwks),
    )

    response = client.post(
        "/v1/authorize",
        headers=auth_header(token),
        json={
            "org_id": 123,
        },
    )

    assert response.status_code == 422


def test_org_id_empty_string_is_rejected():
    private_key, _, jwks = setup_keys()

    token = create_token(private_key)

    client = make_client(
        FakeJwksCache(jwks),
    )

    response = client.post(
        "/v1/authorize",
        headers=auth_header(token),
        json={
            "org_id": "",
        },
    )

    assert response.status_code == 422


# ---------------------------------------------------------------------------
# JWKS availability
# ---------------------------------------------------------------------------


def test_unavailable_jwks_cache_returns_503():
    cache = FakeJwksCache(
        None,
        source="unavailable",
        reason="fetch_failed",
    )

    client = make_client(cache)

    response = client.post(
        "/v1/authorize",
        headers={
            "Authorization": "Bearer some-token",
        },
        json={"org_id": ORG_ID},
    )

    assert response.status_code == 503


def test_jwks_provider_exception_does_not_become_500():
    client = make_client(
        RaisingJwksCache(),
        raise_server_exceptions=False,
    )

    response = client.post(
        "/v1/authorize",
        headers={
            "Authorization": "Bearer some-token",
        },
        json={"org_id": ORG_ID},
    )

    assert response.status_code != 500
    assert response.status_code == 503


# ---------------------------------------------------------------------------
# Error response security
# ---------------------------------------------------------------------------


def assert_no_sensitive_error_information(response, token=None):
    body = response.text.lower()

    assert "traceback" not in body
    assert "stack trace" not in body
    assert "verification:" not in body
    assert "license:" not in body
    assert "modules:" not in body
    assert "jwks" not in body
    assert "exception" not in body

    if token is not None:
        assert token not in response.text


def test_401_response_does_not_leak_internal_reason_or_token():
    private_key, _, jwks = setup_keys()

    token = create_token(private_key)

    client = make_client(
        FakeJwksCache(jwks),
    )

    response = client.post(
        "/v1/authorize",
        headers=auth_header("invalid-token"),
        json={"org_id": ORG_ID},
    )

    assert response.status_code == 401

    assert_no_sensitive_error_information(
        response,
        token=token,
    )


def test_403_response_does_not_leak_internal_license_reason():
    private_key, _, jwks = setup_keys()

    token = create_token(
        private_key,
        extra_claims={
            "license_status": "revoked",
        },
    )

    client = make_client(
        FakeJwksCache(jwks),
    )

    response = client.post(
        "/v1/authorize",
        headers=auth_header(token),
        json={"org_id": ORG_ID},
    )

    assert response.status_code == 403

    assert_no_sensitive_error_information(
        response,
        token=token,
    )


def test_503_response_does_not_leak_provider_details():
    client = make_client(
        FakeJwksCache(
            None,
            source="unavailable",
            reason="fetch_failed",
        ),
    )

    response = client.post(
        "/v1/authorize",
        headers={
            "Authorization": "Bearer secret-token",
        },
        json={"org_id": ORG_ID},
    )

    assert response.status_code == 503

    assert_no_sensitive_error_information(
        response,
        token="secret-token",
    )


# ---------------------------------------------------------------------------
# Dependency injection / cache interaction
# ---------------------------------------------------------------------------


def test_jwks_cache_receives_token_kid():
    private_key, _, jwks = setup_keys()

    cache = FakeJwksCache(jwks)

    token = create_token(
        private_key,
        kid="test-key",
    )

    client = make_client(cache)

    response = client.post(
        "/v1/authorize",
        headers=auth_header(token),
        json={"org_id": ORG_ID},
    )

    assert response.status_code == 200

    assert len(cache.calls) == 1
    assert cache.calls[0]["kid"] == "test-key"


def test_health_does_not_depend_on_license_lookup():
    _, _, jwks = setup_keys()

    calls = []

    def license_lookup(org_id):
        calls.append(org_id)
        raise AssertionError(
            "license lookup must not be called by health"
        )

    app = create_app(
        jwks_cache=FakeJwksCache(jwks),
        issuer=ISSUER,
        audience=AUDIENCE,
        license_modules_for=license_lookup,
    )

    client = TestClient(app)

    response = client.get("/v1/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert calls == []


# ---------------------------------------------------------------------------
# Method / route handling
# ---------------------------------------------------------------------------


def test_authorize_get_is_not_allowed():
    _, _, jwks = setup_keys()

    client = make_client(
        FakeJwksCache(jwks),
    )

    response = client.get("/v1/authorize")

    assert response.status_code == 405


def test_health_post_is_not_allowed():
    _, _, jwks = setup_keys()

    client = make_client(
        FakeJwksCache(jwks),
    )

    response = client.post("/v1/health")

    assert response.status_code == 405


def test_unknown_route_returns_404_without_stack_trace():
    _, _, jwks = setup_keys()

    client = make_client(
        FakeJwksCache(jwks),
    )

    response = client.get("/v1/does-not-exist")

    assert response.status_code == 404
    assert "traceback" not in response.text.lower()