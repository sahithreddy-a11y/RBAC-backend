from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable

import jwt
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, ConfigDict, field_validator

from .authorize import authorize_launch
from .jwks_cache import JwksCache


class AuthorizeRequest(BaseModel):
    """
    Request body for the authorization endpoint.

    Unknown fields are rejected so malformed client requests do not
    silently become valid authorization requests.
    """

    model_config = ConfigDict(extra="forbid")

    org_id: str

    @field_validator("org_id")
    @classmethod
    def validate_org_id(cls, value: str) -> str:
        if not isinstance(value, str):
            raise ValueError("org_id must be a string")

        value = value.strip()

        if not value:
            raise ValueError("org_id must not be empty")

        return value


class AuthorizeResponse(BaseModel):
    allowed: bool
    modules: list[str]
    warning: str | None


def _unauthorized() -> HTTPException:
    """
    Return a deliberately generic authentication error.

    Do not expose whether the token was expired, malformed, signed by
    an unknown key, or otherwise invalid.
    """
    return HTTPException(
        status_code=401,
        detail="unauthorized",
    )


def _forbidden() -> HTTPException:
    """
    Return a deliberately generic authorization error.

    Internal licence/module reason codes must not cross the HTTP boundary.
    """
    return HTTPException(
        status_code=403,
        detail="forbidden",
    )


def _service_unavailable() -> HTTPException:
    """
    Return a deliberately generic infrastructure failure.

    Internal provider/cache exception details must never be exposed.
    """
    return HTTPException(
        status_code=503,
        detail="service unavailable",
    )


def _extract_bearer_token(
    authorization: str | None,
) -> str:
    """
    Extract a bearer token from the Authorization header.

    Accepted format:

        Authorization: Bearer <token>

    Everything else is rejected with 401.
    """

    if not isinstance(authorization, str):
        raise _unauthorized()

    value = authorization.strip()

    if not value:
        raise _unauthorized()

    parts = value.split()

    if len(parts) != 2:
        raise _unauthorized()

    scheme, token = parts

    if scheme.lower() != "bearer":
        raise _unauthorized()

    if not token.strip():
        raise _unauthorized()

    return token


def _extract_kid(token: str) -> str | None:
    """
    Read the JWT header only for JWKS cache selection.

    The JWT header is UNTRUSTED.

    The returned kid is never treated as proof of identity or validity.
    Cryptographic verification remains the responsibility of
    authorize_launch() / verify_token().
    """

    try:
        header = jwt.get_unverified_header(token)
    except Exception:
        return None

    if not isinstance(header, dict):
        return None

    kid = header.get("kid")

    if not isinstance(kid, str):
        return None

    kid = kid.strip()

    if not kid:
        return None

    return kid


def _valid_license_modules(value: object) -> bool:
    """
    Validate the contract of license_modules_for().

    The callback must return a list of module names.
    """

    if not isinstance(value, list):
        return False

    return all(
        isinstance(module, str)
        and bool(module.strip())
        for module in value
    )


def create_app(
    *,
    jwks_cache: JwksCache,
    issuer: str,
    audience: str,
    license_modules_for: Callable[[str], list[str]],
    now: Callable[[], datetime] | None = None,
) -> FastAPI:
    """
    Create the authorization HTTP application.

    All dependencies are supplied through this function.

    There is deliberately no module-level authorization state.
    """


    if not isinstance(issuer, str) or not issuer.strip():
        raise ValueError("issuer must be a non-empty string")

    if not isinstance(audience, str) or not audience.strip():
        raise ValueError("audience must be a non-empty string")

    if not callable(license_modules_for):
        raise TypeError(
            "license_modules_for must be callable"
        )

    if now is not None and not callable(now):
        raise TypeError(
            "now must be callable"
        )

    clock = now or (lambda: datetime.now(timezone.utc))

    app = FastAPI()

    @app.get("/v1/health")
    def health() -> dict[str, str]:
        """
        Health endpoint.

        This endpoint intentionally requires no authentication.
        """
        return {"status": "ok"}

    @app.post(
        "/v1/authorize",
        response_model=AuthorizeResponse,
    )
    def authorize(
        request: AuthorizeRequest,
        authorization: str | None = Header(
            default=None,
            alias="Authorization",
        ),
    ) -> AuthorizeResponse:
        """
        Authorize an application launch.

        HTTP boundary:

            401 -> authentication failed
            403 -> authenticated but not authorized
            422 -> malformed request body
            503 -> required infrastructure unavailable

        Internal authorization reasons never cross this boundary.
        """

        # ---------------------------------------------------------
        # 1. Extract and validate bearer token
        # ---------------------------------------------------------

        token = _extract_bearer_token(authorization)

        # ---------------------------------------------------------
        # 2. Obtain the appropriate JWKS from the cache
        # ---------------------------------------------------------

        kid = _extract_kid(token)

        try:
            current_time = clock()

            cache_result = jwks_cache.get(
                now=current_time,
                kid=kid,
            )
        except Exception:
            # Cache/provider failures are infrastructure failures.
            raise _service_unavailable()

        if cache_result.source == "unavailable":
            raise _service_unavailable()

        if cache_result.jwks is None:
            raise _service_unavailable()

        if not isinstance(cache_result.jwks, dict):
            raise _service_unavailable()

        # ---------------------------------------------------------
        # 3. Resolve licence modules
        # ---------------------------------------------------------
        #
        # This is injected rather than implemented here.
        # The endpoint must not know how licences are stored.
        # ---------------------------------------------------------

        try:
            license_modules = license_modules_for(
                request.org_id
            )
        except Exception:
            # Do not expose database/provider details.
            raise _service_unavailable()

        if not _valid_license_modules(license_modules):
            raise _service_unavailable()

        # Defensive copy: do not allow the callback's returned list
        # to be modified during authorization.
        license_modules = list(license_modules)

        # ---------------------------------------------------------
        # 4. Run the existing authorization pipeline
        # ---------------------------------------------------------
        #
        # Do NOT duplicate:
        #   - JWT verification
        #   - claims parsing
        #   - licence evaluation
        #   - module resolution
        #
        # authorize_launch() owns those decisions.
        # ---------------------------------------------------------

        try:
            result = authorize_launch(
                token,
                cache_result.jwks,
                issuer=issuer,
                audience=audience,
                license_modules=license_modules,
                now=current_time,
            )
        except Exception:
            # Nothing from an internal exception should reach the
            # client. This prevents accidental 500s and stack traces.
            raise _service_unavailable()

        # ---------------------------------------------------------
        # 5. Map internal authorization decisions to HTTP semantics
        # ---------------------------------------------------------

        if not result.allowed:
            if result.reason.startswith("verification:"):
                raise _unauthorized()

            if result.reason.startswith("license:"):
                raise _forbidden()

            if result.reason.startswith("modules:"):
                raise _forbidden()

            # Unknown internal denial reasons fail closed.
            raise _forbidden()

        # ---------------------------------------------------------
        # 6. Successful authorization
        # ---------------------------------------------------------

        modules = list(result.modules)

        return AuthorizeResponse(
            allowed=True,
            modules=modules,
            warning=result.warning,
        )

    return app