from dataclasses import dataclass

import jwt
from jwt import (
    ExpiredSignatureError,
    ImmatureSignatureError,
    InvalidAudienceError,
    InvalidIssuerError,
    InvalidSignatureError,
    InvalidTokenError,
)


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
) -> VerifiedToken:
    """Verify a JWT using an in-memory JWKS.

    The token must:
    - be a non-empty string
    - use RS256
    - contain a known kid
    - use an RSA signing key
    - have a valid signature
    - contain a valid exp claim
    - not be before nbf, when nbf is present
    - contain the expected issuer
    - contain the expected audience
    - contain the expected token_use

    Invalid or untrusted input is returned as a VerifiedToken with
    valid=False rather than being allowed to escape as an exception.
    """

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

    # The algorithm is NOT negotiated with the token.
    # RS256 is the only algorithm this verifier accepts.
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
    # Validate the selected JWK before using it
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
    # Cryptographic verification + registered claim validation
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
            },
        )

    except ExpiredSignatureError:
        return _invalid("expired")

    except ImmatureSignatureError:
        return _invalid("not_yet_valid")

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
    # Application-specific token_use claim
    # ---------------------------------------------------------

    if claims.get("token_use") != token_use:
        return _invalid("wrong_token_use")

    # ---------------------------------------------------------
    # Everything passed
    # ---------------------------------------------------------

    return VerifiedToken(
        valid=True,
        claims=claims,
        reason="ok",
    )