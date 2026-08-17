"""
Application launch authorization.

Task 11 composition pipeline:

    verify_token()
        ↓
    parse_claims()
        ↓
    evaluate_license()
        ↓
    resolve_user_modules()
        ↓
    AuthorizationResult

The order is security-critical:
claims must never be parsed/trusted before JWT verification succeeds.
"""

from dataclasses import dataclass
from datetime import datetime, timezone

from .claims import parse_claims
from .jwt_verify import verify_token
from .license_status import evaluate_license
from .modules import resolve_user_modules


@dataclass(frozen=True)
class AuthorizationResult:
    allowed: bool
    modules: list[str]
    reason: str
    user_email: str | None
    role: str | None
    warning: str | None


def _denied(
    reason: str,
    *,
    user_email: str | None = None,
    role: str | None = None,
    warning: str | None = None,
) -> AuthorizationResult:
    return AuthorizationResult(
        allowed=False,
        modules=[],
        reason=reason,
        user_email=user_email,
        role=role,
        warning=warning,
    )


def _normalize_now(now: datetime | None) -> datetime:
    """
    Normalize the single authorization clock to UTC.

    Naive datetimes are interpreted as UTC, matching the existing
    license/session implementations.
    """
    if now is None:
        return datetime.now(timezone.utc)

    if not isinstance(now, datetime):
        raise TypeError("now must be a datetime or None")

    if now.tzinfo is None:
        return now.replace(tzinfo=timezone.utc)

    return now.astimezone(timezone.utc)


def authorize_launch(
    token: str,
    jwks: dict,
    *,
    issuer: str,
    audience: str,
    license_modules: list[str],
    now: datetime | None = None,
) -> AuthorizationResult:
    """
    Determine what an authenticated user may do at application launch.

    Pipeline:

        1. Verify JWT.
        2. Parse verified claims.
        3. Evaluate license.
        4. Resolve requested modules.

    Any failed stage immediately stops the pipeline.
    """

    # ---------------------------------------------------------
    # INPUT VALIDATION
    # ---------------------------------------------------------

    if not isinstance(token, str) or not token.strip():
        return _denied("verification:malformed")

    if not isinstance(jwks, dict):
        return _denied("verification:malformed")

    if not isinstance(issuer, str) or not issuer:
        return _denied("verification:malformed")

    if not isinstance(audience, str) or not audience:
        return _denied("verification:malformed")

    if not isinstance(license_modules, list):
        return _denied("modules:invalid_license_modules")

    # Defensive copy so the caller cannot mutate the list during
    # this authorization operation.
    requested_license_modules = list(license_modules)

    try:
        operation_now = _normalize_now(now)
    except TypeError:
        return _denied("authorization:invalid_now")

    # ---------------------------------------------------------
    # STEP 1 — VERIFY JWT
    #
    # Claims must not be parsed or trusted before verification.
    # ---------------------------------------------------------

    verified = verify_token(
        token,
        jwks,
        issuer=issuer,
        audience=audience,
    )

    if not verified.valid:
        return _denied(f"verification:{verified.reason}")

    if not isinstance(verified.claims, dict):
        return _denied("verification:invalid_claims")

    # ---------------------------------------------------------
    # STEP 2 — PARSE VERIFIED CLAIMS
    # ---------------------------------------------------------

    try:
        claims = parse_claims(verified.claims)
    except (ValueError, TypeError):
        return _denied("claims:invalid")

    user_email = claims.email
    role = claims.role

    # ---------------------------------------------------------
    # STEP 3 — LICENSE EVALUATION
    #
    # license_status is part of the real Claims model.
    #
    # getattr(..., "active") is intentionally used here because
    # some authorization tests use lightweight mock Claims
    # objects that predate the license_status field.
    #
    # Real parsed claims always provide license_status because
    # parse_claims() defaults a missing status to "active".
    # ---------------------------------------------------------

    license_status_claim = claims.license_status

    try:
        license_status = evaluate_license(
            license_status_claim,
            claims.license_expires,
            operation_now,
        )
    except (ValueError, TypeError, OverflowError):
        return _denied(
            "license:evaluation_failed",
            user_email=user_email,
            role=role,
        )

    if not license_status.valid:
        return _denied(
            f"license:{license_status.reason}",
            user_email=user_email,
            role=role,
        )

    # ---------------------------------------------------------
    # LICENSE WARNING
    # ---------------------------------------------------------

    warning = None

    if license_status.show_warning:
        if license_status.days_remaining is not None:
            warning = (
                f"Licence expires in "
                f"{license_status.days_remaining} days"
            )

    # ---------------------------------------------------------
    # STEP 4 — MODULE RESOLUTION
    #
    # claims.modules comes from the verified JWT.
    #
    # resolve_user_modules() handles:
    #   - unknown modules
    #   - unlicensed modules
    #   - duplicates
    #   - cross_compare dependency
    # ---------------------------------------------------------

    try:
        resolution = resolve_user_modules(
            requested_license_modules,
            claims.modules,
        )
    except (ValueError, TypeError):
        return _denied(
            "modules:resolution_failed",
            user_email=user_email,
            role=role,
            warning=warning,
        )

    # ---------------------------------------------------------
    # SUCCESS
    # ---------------------------------------------------------

    return AuthorizationResult(
        allowed=True,
        modules=list(resolution.granted),
        reason="ok",
        user_email=user_email,
        role=role,
        warning=warning,
    )