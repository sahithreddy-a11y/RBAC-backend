from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Callable


DEFAULT_TTL = timedelta(hours=12)
MIN_REFETCH_INTERVAL = timedelta(minutes=5)


@dataclass(frozen=True)
class CacheResult:
    jwks: dict | None
    source: str
    reason: str


class JwksCache:
    """
    In-memory JWKS cache with TTL and rotation handling.

    Unknown-kid refreshes are rate-limited so an attacker cannot cause
    an outbound fetch for every arbitrary kid.

    The rate limit applies only to refreshes triggered by an unknown kid.
    The initial cold-cache fetch and normal TTL-expiry refresh are not
    counted as unknown-kid refresh attempts.

    Stale-cache fetch failures fail closed rather than continuing to
    trust expired key material.
    """

    def __init__(
        self,
        fetcher: Callable[[], dict],
        *,
        ttl: timedelta = DEFAULT_TTL,
        min_refetch_interval: timedelta = MIN_REFETCH_INTERVAL,
    ) -> None:
        if not callable(fetcher):
            raise TypeError("fetcher must be callable")

        if ttl < timedelta(0):
            raise ValueError("ttl must be non-negative")

        if min_refetch_interval < timedelta(0):
            raise ValueError(
                "min_refetch_interval must be non-negative"
            )

        self._fetcher = fetcher
        self._ttl = ttl
        self._min_refetch_interval = min_refetch_interval

        self._jwks: dict | None = None
        self._fetched_at: datetime | None = None

        # Tracks only unknown-kid-triggered refresh attempts.
        self._last_refetch_attempt: datetime | None = None

    def get(
        self,
        *,
        now: datetime,
        kid: str | None = None,
    ) -> CacheResult:
        now = self._normalize_now(now)

        # ---------------------------------------------------------
        # Cold cache
        # ---------------------------------------------------------
        if self._jwks is None or self._fetched_at is None:
            return self._fetch(
                now,
                reason="cold_cache",
            )

        age = now - self._fetched_at

        # A clock moving backwards should not make old key material
        # appear newer than it really is.
        if age < timedelta(0):
            age = timedelta(0)

        # ---------------------------------------------------------
        # TTL expired
        # ---------------------------------------------------------
        if age >= self._ttl:
            return self._fetch(
                now,
                reason="ttl_expired",
            )

        # ---------------------------------------------------------
        # Cache is fresh and no kid was supplied.
        # ---------------------------------------------------------
        if kid is None:
            return CacheResult(
                jwks=self._jwks,
                source="cache",
                reason="within_ttl",
            )

        # ---------------------------------------------------------
        # Known kid: never refresh while cache is fresh.
        # ---------------------------------------------------------
        if self._contains_kid(self._jwks, kid):
            return CacheResult(
                jwks=self._jwks,
                source="cache",
                reason="known_kid",
            )

        # ---------------------------------------------------------
        # Unknown kid:
        #
        # This can indicate key rotation, so attempt a refresh.
        # However, unknown-kid refreshes are rate-limited.
        # ---------------------------------------------------------
        if self._last_refetch_attempt is not None:
            since_last_attempt = now - self._last_refetch_attempt

            if since_last_attempt < timedelta(0):
                since_last_attempt = timedelta(0)

            if since_last_attempt < self._min_refetch_interval:
                return CacheResult(
                    jwks=self._jwks,
                    source="cache",
                    reason="unknown_kid_refetch_rate_limited",
                )

        return self._fetch(
            now,
            reason="unknown_kid",
        )

    def _fetch(
        self,
        now: datetime,
        *,
        reason: str,
    ) -> CacheResult:
        # Only unknown-kid-triggered fetches participate in the
        # unknown-kid refresh rate limit.
        if reason == "unknown_kid":
            self._last_refetch_attempt = now

        try:
            fetched = self._fetcher()
        except Exception:
            # Cold-cache failure: nothing is available.
            #
            # Stale-cache failure: fail closed rather than returning
            # expired key material.
            return CacheResult(
                jwks=None,
                source="unavailable",
                reason="fetch_failed",
            )

        # Never allow invalid fetch results to poison the cache.
        if not self._is_valid_jwks(fetched):
            return CacheResult(
                jwks=None,
                source="unavailable",
                reason="invalid_jwks",
            )

        # Replace the cache only after successful validation.
        self._jwks = fetched
        self._fetched_at = now

        return CacheResult(
            jwks=fetched,
            source="fetch",
            reason=reason,
        )

    @staticmethod
    def _normalize_now(now: datetime) -> datetime:
        if not isinstance(now, datetime):
            raise TypeError("now must be a datetime")

        if now.tzinfo is None:
            raise ValueError("now must be timezone-aware")

        return now

    @staticmethod
    def _is_valid_jwks(jwks: object) -> bool:
        if not isinstance(jwks, dict):
            return False

        keys = jwks.get("keys")

        if not isinstance(keys, list):
            return False

        if not keys:
            return False

        for key in keys:
            if not isinstance(key, dict):
                return False

            if not isinstance(key.get("kid"), str):
                return False

        return True

    @staticmethod
    def _contains_kid(
        jwks: dict,
        kid: str,
    ) -> bool:
        keys = jwks.get("keys")

        if not isinstance(keys, list):
            return False

        return any(
            isinstance(key, dict) and key.get("kid") == kid
            for key in keys
        )