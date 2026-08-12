from datetime import datetime, timedelta, timezone

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa

from backend.src.rbac.jwt_verify import verify_token


ISSUER = "https://issuer.example.com"
AUDIENCE = "biovaram-api"
TOKEN_USE = "id"


def generate_key_pair():
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
    )

    public_key = private_key.public_key()

    return private_key, public_key


def public_jwk(public_key, kid="test-key"):
    from jwt.algorithms import RSAAlgorithm

    jwk = RSAAlgorithm.to_jwk(public_key)

    import json

    key = json.loads(jwk)
    key["kid"] = kid
    key["alg"] = "RS256"
    key["use"] = "sig"

    return key


def create_token(
    private_key,
    *,
    kid="test-key",
    issuer=ISSUER,
    audience=AUDIENCE,
    token_use=TOKEN_USE,
    expires_delta=timedelta(minutes=10),
    not_before=None,
    extra_claims=None,
):
    now = datetime.now(timezone.utc)

    payload = {
        "sub": "user-123",
        "iss": issuer,
        "aud": audience,
        "exp": now + expires_delta,
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
        headers={"kid": kid},
    )


def test_valid_token_is_verified():
    private_key, public_key = generate_key_pair()

    token = create_token(private_key)

    jwks = {
        "keys": [
            public_jwk(public_key),
        ]
    }

    result = verify_token(
        token,
        jwks,
        issuer=ISSUER,
        audience=AUDIENCE,
    )

    assert result.valid is True
    assert result.reason == "ok"
    assert result.claims is not None
    assert result.claims["sub"] == "user-123"


def test_bad_signature_is_rejected():
    private_key, public_key = generate_key_pair()
    attacker_private_key, _ = generate_key_pair()

    token = create_token(attacker_private_key)

    jwks = {
        "keys": [
            public_jwk(public_key),
        ]
    }

    result = verify_token(
        token,
        jwks,
        issuer=ISSUER,
        audience=AUDIENCE,
    )

    assert result.valid is False
    assert result.claims is None
    assert result.reason == "bad_signature"


def test_expired_token_is_rejected():
    private_key, public_key = generate_key_pair()

    token = create_token(
        private_key,
        expires_delta=timedelta(seconds=-1),
    )

    jwks = {
        "keys": [
            public_jwk(public_key),
        ]
    }

    result = verify_token(
        token,
        jwks,
        issuer=ISSUER,
        audience=AUDIENCE,
    )

    assert result.valid is False
    assert result.claims is None
    assert result.reason == "expired"


def test_not_yet_valid_token_is_rejected():
    private_key, public_key = generate_key_pair()

    future_time = datetime.now(timezone.utc) + timedelta(minutes=10)

    token = create_token(
        private_key,
        not_before=future_time,
    )

    jwks = {
        "keys": [
            public_jwk(public_key),
        ]
    }

    result = verify_token(
        token,
        jwks,
        issuer=ISSUER,
        audience=AUDIENCE,
    )

    assert result.valid is False
    assert result.claims is None
    assert result.reason == "not_yet_valid"


def test_wrong_issuer_is_rejected():
    private_key, public_key = generate_key_pair()

    token = create_token(
        private_key,
        issuer="https://attacker.example.com",
    )

    jwks = {
        "keys": [
            public_jwk(public_key),
        ]
    }

    result = verify_token(
        token,
        jwks,
        issuer=ISSUER,
        audience=AUDIENCE,
    )

    assert result.valid is False
    assert result.claims is None
    assert result.reason == "wrong_issuer"


def test_wrong_audience_is_rejected():
    private_key, public_key = generate_key_pair()

    token = create_token(
        private_key,
        audience="different-api",
    )

    jwks = {
        "keys": [
            public_jwk(public_key),
        ]
    }

    result = verify_token(
        token,
        jwks,
        issuer=ISSUER,
        audience=AUDIENCE,
    )

    assert result.valid is False
    assert result.claims is None
    assert result.reason == "wrong_audience"


def test_wrong_token_use_is_rejected():
    private_key, public_key = generate_key_pair()

    token = create_token(
        private_key,
        token_use="access",
    )

    jwks = {
        "keys": [
            public_jwk(public_key),
        ]
    }

    result = verify_token(
        token,
        jwks,
        issuer=ISSUER,
        audience=AUDIENCE,
    )

    assert result.valid is False
    assert result.claims is None
    assert result.reason == "wrong_token_use"


def test_unknown_kid_is_rejected():
    private_key, public_key = generate_key_pair()

    token = create_token(
        private_key,
        kid="unknown-key",
    )

    jwks = {
        "keys": [
            public_jwk(public_key, kid="different-key"),
        ]
    }

    result = verify_token(
        token,
        jwks,
        issuer=ISSUER,
        audience=AUDIENCE,
    )

    assert result.valid is False
    assert result.claims is None
    assert result.reason == "unknown_kid"


def test_none_algorithm_is_rejected():
    private_key, public_key = generate_key_pair()

    payload = {
        "sub": "user-123",
        "iss": ISSUER,
        "aud": AUDIENCE,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=10),
        "token_use": TOKEN_USE,
    }

    token = jwt.encode(
        payload,
        key="",
        algorithm="none",
        headers={"kid": "test-key"},
    )

    jwks = {
        "keys": [
            public_jwk(public_key),
        ]
    }

    result = verify_token(
        token,
        jwks,
        issuer=ISSUER,
        audience=AUDIENCE,
    )

    assert result.valid is False
    assert result.claims is None
    assert result.reason == "unsupported_algorithm"


def test_hs256_algorithm_is_rejected():
    private_key, public_key = generate_key_pair()

    payload = {
        "sub": "user-123",
        "iss": ISSUER,
        "aud": AUDIENCE,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=10),
        "token_use": TOKEN_USE,
    }

    token = jwt.encode(
        payload,
        "attacker-secret-that-is-at-least-32-bytes-long",
        algorithm="HS256",
        headers={"kid": "test-key"},
    )

    jwks = {
        "keys": [
            public_jwk(public_key),
        ]
    }

    result = verify_token(
        token,
        jwks,
        issuer=ISSUER,
        audience=AUDIENCE,
    )

    assert result.valid is False
    assert result.claims is None
    assert result.reason == "unsupported_algorithm"


def test_malformed_token_does_not_raise():
    private_key, public_key = generate_key_pair()

    jwks = {
        "keys": [
            public_jwk(public_key),
        ]
    }

    result = verify_token(
        "this-is-not-a-jwt",
        jwks,
        issuer=ISSUER,
        audience=AUDIENCE,
    )

    assert result.valid is False
    assert result.claims is None
    assert result.reason == "malformed"


def test_missing_exp_is_rejected():
    private_key, public_key = generate_key_pair()

    payload = {
        "sub": "user-123",
        "iss": ISSUER,
        "aud": AUDIENCE,
        "token_use": TOKEN_USE,
    }

    token = jwt.encode(
        payload,
        private_key,
        algorithm="RS256",
        headers={"kid": "test-key"},
    )

    jwks = {
        "keys": [
            public_jwk(public_key),
        ]
    }

    result = verify_token(
        token,
        jwks,
        issuer=ISSUER,
        audience=AUDIENCE,
    )

    assert result.valid is False
    assert result.claims is None
    assert result.reason == "malformed"


def test_missing_issuer_is_rejected():
    private_key, public_key = generate_key_pair()

    now = datetime.now(timezone.utc)

    payload = {
        "sub": "user-123",
        "aud": AUDIENCE,
        "exp": now + timedelta(minutes=10),
        "token_use": TOKEN_USE,
    }

    token = jwt.encode(
        payload,
        private_key,
        algorithm="RS256",
        headers={"kid": "test-key"},
    )

    jwks = {
        "keys": [
            public_jwk(public_key),
        ]
    }

    result = verify_token(
        token,
        jwks,
        issuer=ISSUER,
        audience=AUDIENCE,
    )

    assert result.valid is False
    assert result.claims is None
    assert result.reason == "malformed"


def test_missing_audience_is_rejected():
    private_key, public_key = generate_key_pair()

    now = datetime.now(timezone.utc)

    payload = {
        "sub": "user-123",
        "iss": ISSUER,
        "exp": now + timedelta(minutes=10),
        "token_use": TOKEN_USE,
    }

    token = jwt.encode(
        payload,
        private_key,
        algorithm="RS256",
        headers={"kid": "test-key"},
    )

    jwks = {
        "keys": [
            public_jwk(public_key),
        ]
    }

    result = verify_token(
        token,
        jwks,
        issuer=ISSUER,
        audience=AUDIENCE,
    )

    assert result.valid is False
    assert result.claims is None
    assert result.reason == "malformed"