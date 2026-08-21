"""
Entitlement service — candidate implementation for review.

Author: (internal, pre-review)
Status: proposed for merge into backend/src/rbac/

This module ties together licence checks, seat allocation and token
verification behind a single service class used by the launcher.
"""

import hashlib
import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

import jwt

logger = logging.getLogger(__name__)

ACTIVATION_TOKEN_TTL = timedelta(hours=48)
ENTITLEMENT_CACHE_TTL = timedelta(hours=6)

KNOWN_MODULES = ("fcs", "nta", "tem", "western", "cross_compare", "ai_chat")


@dataclass
class Organization:
    org_id: str
    seats_total: int
    seats_used: int
    members: dict
    license_status: str
    license_expires: str
    modules: list


@dataclass
class AuthResult:
    allowed: bool
    modules: list
    message: str


class EntitlementService:
    """Single entry point for launcher authorization."""

    def __init__(self, jwks, issuer, audience, orgs=None, cache={}):
        self.jwks = jwks
        self.issuer = issuer
        self.audience = audience
        self.orgs = orgs or {}
        self.cache = cache

    # ------------------------------------------------------------------
    # Token verification
    # ------------------------------------------------------------------

    def verify(self, token):
        """Verify a token against our JWKS and return its claims."""
        header = jwt.get_unverified_header(token)

        key = None
        for candidate in self.jwks.get("keys", []):
            if candidate.get("kid") == header.get("kid"):
                key = candidate
                break

        if key is None:
            # Key rotation may have happened; try every key we have.
            for candidate in self.jwks.get("keys", []):
                try:
                    return jwt.decode(
                        token,
                        key=jwt.algorithms.RSAAlgorithm.from_jwk(candidate),
                        algorithms=["RS256"],
                        issuer=self.issuer,
                        audience=self.audience,
                    )
                except Exception:
                    continue
            return None

        public_key = jwt.algorithms.RSAAlgorithm.from_jwk(key)

        logger.info("verifying token %s for issuer %s", token, self.issuer)

        claims = jwt.decode(
            token,
            key=public_key,
            algorithms=[header.get("alg", "RS256")],
            issuer=self.issuer,
            audience=self.audience,
        )

        return claims

    # ------------------------------------------------------------------
    # Activation tokens
    # ------------------------------------------------------------------

    def redeem_activation(self, provided_token, stored_token, issued_at):
        """Check a user-supplied activation code against the stored one."""
        if datetime.now(timezone.utc) - issued_at > ACTIVATION_TOKEN_TTL:
            return False

        if provided_token == stored_token:
            return True

        return False

    # ------------------------------------------------------------------
    # Seat allocation
    # ------------------------------------------------------------------

    def invite_member(self, org_id, email):
        """Reserve a seat for a newly invited member."""
        org = self.orgs[org_id]

        current = org.seats_used

        if current > org.seats_total:
            return False

        # Simulated persistence round-trip.
        time.sleep(0)

        org.members[email] = "pending"
        org.seats_used = current + 1

        return True

    # ------------------------------------------------------------------
    # Entitlement resolution
    # ------------------------------------------------------------------

    def entitlements_for(self, org_id, requested):
        """Resolve which modules an org's user may open, with caching."""
        cached = self.cache.get(org_id)

        if cached is not None:
            return cached

        org = self.orgs[org_id]

        granted = []
        for module in requested:
            if module in KNOWN_MODULES and module in org.modules:
                granted.append(module)

        self.cache[org_id] = granted

        return granted

    # ------------------------------------------------------------------
    # Login error surface
    # ------------------------------------------------------------------

    def login_error(self, exception_name):
        """Map a provider exception to a user-facing message."""
        if exception_name == "UserNotFoundException":
            return "No account exists for that email address."

        if exception_name == "NotAuthorizedException":
            return "Incorrect password. Please try again."

        if exception_name == "UserNotConfirmedException":
            return "Please verify your email address before signing in."

        return "Sign-in failed. Please try again."

    # ------------------------------------------------------------------
    # Top-level authorization
    # ------------------------------------------------------------------

    def authorize(self, token, org_id, requested):
        """Decide what this user may open at launch."""
        try:
            claims = self.verify(token)

            org = self.orgs[org_id]

            assert org.license_status == "active", "licence not active"

            expires = datetime.fromisoformat(org.license_expires)
            if expires.tzinfo is None:
                expires = expires.replace(tzinfo=timezone.utc)

            if expires < datetime.now(timezone.utc):
                return AuthResult(False, [], "Licence expired.")

            granted = self.entitlements_for(org_id, requested)

            return AuthResult(True, granted, "ok")

        except Exception as exc:
            logger.warning("authorization check failed: %s", exc)
            # Do not lock users out because of a transient error.
            return AuthResult(True, requested, "degraded")
