from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import jwt
from jwt import (
    ExpiredSignatureError,
    ImmatureSignatureError,
    InvalidAudienceError,
    InvalidIssuerError,
    InvalidSignatureError,
    InvalidTokenError,
)


CLOCK_SKEW_SECONDS = 60


@dataclass(frozen=True)
class VerifiedToken:
    valid: bool
    claims: dict | None
    reason: str


def _invalid(reason: str) -> VerifiedToken:
    return VerifiedToken(
        valid=False,
        claims=None,
        reason=reason,
    )


def verify_token(
    token: str,
    jwks: dict,
    *,
    issuer: str,
    audience: str,
    token_use: str = "id",
    now: datetime | None = None,
) -> VerifiedToken:
    """Verify a JWT using an in-memory JWKS.

    Time-based claims use a 60-second clock-skew tolerance.

    ``now`` is injectable so callers and tests can control the reference
    time used for exp and nbf validation.
    """

    if now is None:
        now = datetime.now(timezone.utc)

    if not isinstance(now, datetime):
        return _invalid("malformed")

    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    now = now.astimezone(timezone.utc)

    # ---------------------------------------------------------
    # Basic input validation
    # ---------------------------------------------------------

    if not isinstance(token, str) or not token.strip():
        return _invalid("malformed")

    if not isinstance(jwks, dict):
        return _invalid("malformed")

    if not isinstance(issuer, str) or not issuer:
        return _invalid("malformed")

    if not isinstance(audience, str) or not audience:
        return _invalid("malformed")

    if not isinstance(token_use, str) or not token_use:
        return _invalid("malformed")

    # ---------------------------------------------------------
    # Read JWT header without trusting it
    # ---------------------------------------------------------

    try:
        header = jwt.get_unverified_header(token)
    except (InvalidTokenError, ValueError, TypeError):
        return _invalid("malformed")

    if not isinstance(header, dict):
        return _invalid("malformed")

    algorithm = header.get("alg")
    kid = header.get("kid")

    if algorithm != "RS256":
        return _invalid("unsupported_algorithm")

    if not isinstance(kid, str) or not kid.strip():
        return _invalid("unknown_kid")

    # ---------------------------------------------------------
    # Find the exact key identified by kid
    # ---------------------------------------------------------

    keys = jwks.get("keys")

    if not isinstance(keys, list):
        return _invalid("unknown_kid")

    matching_key = None

    for key in keys:
        if not isinstance(key, dict):
            continue

        if key.get("kid") == kid:
            matching_key = key
            break

    if matching_key is None:
        return _invalid("unknown_kid")

    # ---------------------------------------------------------
    # Validate the selected JWK
    # ---------------------------------------------------------

    if matching_key.get("kty") != "RSA":
        return _invalid("malformed")

    key_algorithm = matching_key.get("alg")

    if key_algorithm is not None and key_algorithm != "RS256":
        return _invalid("unsupported_algorithm")

    if matching_key.get("use") is not None and matching_key.get("use") != "sig":
        return _invalid("malformed")

    try:
        public_key = jwt.algorithms.RSAAlgorithm.from_jwk(matching_key)
    except (ValueError, TypeError, KeyError):
        return _invalid("malformed")

    # ---------------------------------------------------------
    # Cryptographic verification + issuer/audience validation
    #
    # exp and nbf are disabled here because PyJWT uses its own
    # internal clock. We validate them below using ``now``.
    # ---------------------------------------------------------

    try:
        claims = jwt.decode(
            token,
            key=public_key,
            algorithms=["RS256"],
            issuer=issuer,
            audience=audience,
            options={
                "require": [
                    "exp",
                    "iss",
                    "aud",
                ],
                "verify_exp": False,
                "verify_nbf": False,
            },
        )

    except InvalidIssuerError:
        return _invalid("wrong_issuer")

    except InvalidAudienceError:
        return _invalid("wrong_audience")

    except InvalidSignatureError:
        return _invalid("bad_signature")

    except InvalidTokenError:
        return _invalid("malformed")

    except (TypeError, ValueError, KeyError):
        return _invalid("malformed")

    # ---------------------------------------------------------
    # Validate exp using injectable now
    # ---------------------------------------------------------

    exp = claims.get("exp")

    if isinstance(exp, bool) or not isinstance(exp, (int, float)):
        return _invalid("malformed")

    try:
       expiration_time = datetime.fromtimestamp(
          exp,
          tz=timezone.utc,
        )
    except (OverflowError, ValueError):
        return _invalid("malformed")

    # Exactly 60 seconds of clock skew is accepted.
    if now > expiration_time + timedelta(seconds=CLOCK_SKEW_SECONDS):
        return _invalid("expired")

    # ---------------------------------------------------------
    # Validate nbf using injectable now
    # ---------------------------------------------------------

    nbf = claims.get("nbf")

    if nbf is not None:
        if isinstance(nbf, bool) or not isinstance(nbf, (int, float)):
            return _invalid("malformed")

        try:
            not_before_time = datetime.fromtimestamp(
               nbf,
               tz=timezone.utc,
            )
        except (OverflowError, ValueError):
            return _invalid("malformed")

        # A token is rejected only when it is more than 60 seconds
        # ahead of the verifier's clock.
        if now < not_before_time - timedelta(seconds=CLOCK_SKEW_SECONDS):
            return _invalid("not_yet_valid")

    # ---------------------------------------------------------
    # Application-specific token_use claim
    # ---------------------------------------------------------

    if claims.get("token_use") != token_use:
        return _invalid("wrong_token_use")

    return VerifiedToken(
        valid=True,
        claims=claims,
        reason="ok",
    )