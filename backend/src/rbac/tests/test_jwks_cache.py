from datetime import datetime, timedelta, timezone

import pytest

from backend.src.rbac.jwks_cache import (
    DEFAULT_TTL,
    MIN_REFETCH_INTERVAL,
    JwksCache,
)


BASE_TIME = datetime(2026, 8, 13, 10, 0, 0, tzinfo=timezone.utc)


def make_jwks(*kids: str) -> dict:
    return {
        "keys": [
            {
                "kid": kid,
                "kty": "RSA",
                "alg": "RS256",
                "use": "sig",
            }
            for kid in kids
        ]
    }


class FakeFetcher:
    def __init__(self, jwks: dict | None = None):
        self.calls = 0
        self.jwks = jwks
        self.error = None

    def __call__(self) -> dict:
        self.calls += 1

        if self.error is not None:
            raise self.error

        return self.jwks


def test_empty_cache_fetches():
    fetcher = FakeFetcher(make_jwks("key-1"))
    cache = JwksCache(fetcher)

    result = cache.get(now=BASE_TIME)

    assert result.source == "fetch"
    assert result.reason == "cold_cache"
    assert result.jwks == make_jwks("key-1")
    assert fetcher.calls == 1


def test_fresh_cache_does_not_fetch_again():
    fetcher = FakeFetcher(make_jwks("key-1"))
    cache = JwksCache(fetcher)

    first = cache.get(now=BASE_TIME)

    fetcher.jwks = make_jwks("key-2")

    second = cache.get(
        now=BASE_TIME + timedelta(hours=1)
    )

    assert first.jwks == make_jwks("key-1")
    assert second.source == "cache"
    assert second.reason == "within_ttl"
    assert second.jwks == make_jwks("key-1")
    assert fetcher.calls == 1


def test_known_kid_within_ttl_does_not_fetch():
    fetcher = FakeFetcher(make_jwks("key-1", "key-2"))
    cache = JwksCache(fetcher)

    cache.get(now=BASE_TIME)

    result = cache.get(
        now=BASE_TIME + timedelta(hours=1),
        kid="key-2",
    )

    assert result.source == "cache"
    assert result.reason == "known_kid"
    assert result.jwks == make_jwks("key-1", "key-2")
    assert fetcher.calls == 1


def test_unknown_kid_triggers_refresh_inside_ttl():
    fetcher = FakeFetcher(make_jwks("old-key"))
    cache = JwksCache(fetcher)

    cache.get(now=BASE_TIME)

    fetcher.jwks = make_jwks("old-key", "new-key")

    result = cache.get(
        now=BASE_TIME + timedelta(minutes=1),
        kid="new-key",
    )

    assert result.source == "fetch"
    assert result.reason == "unknown_kid"
    assert result.jwks == make_jwks("old-key", "new-key")
    assert fetcher.calls == 2


def test_unknown_kid_refetch_is_rate_limited():
    fetcher = FakeFetcher(make_jwks("key-1"))
    cache = JwksCache(fetcher)

    cache.get(now=BASE_TIME)

    result = cache.get(
        now=BASE_TIME + timedelta(minutes=1),
        kid="random-key",
    )

    assert result.source == "fetch"
    assert fetcher.calls == 2

    result = cache.get(
        now=BASE_TIME + timedelta(minutes=2),
        kid="another-random-key",
    )

    assert result.source == "cache"
    assert result.reason == "unknown_kid_refetch_rate_limited"
    assert fetcher.calls == 2


def test_unknown_kid_can_refetch_again_after_rate_limit():
    fetcher = FakeFetcher(make_jwks("key-1"))
    cache = JwksCache(fetcher)

    cache.get(now=BASE_TIME)

    cache.get(
        now=BASE_TIME + timedelta(minutes=1),
        kid="random-key",
    )

    result = cache.get(
        now=BASE_TIME + timedelta(minutes=6),
        kid="another-random-key",
    )

    assert result.source == "fetch"
    assert result.reason == "unknown_kid"
    assert fetcher.calls == 3


def test_one_unknown_kid_fetch_allows_new_kid_to_be_found():
    fetcher = FakeFetcher(make_jwks("old-key"))
    cache = JwksCache(fetcher)

    cache.get(now=BASE_TIME)

    fetcher.jwks = make_jwks("old-key", "new-key")

    first = cache.get(
        now=BASE_TIME + timedelta(minutes=1),
        kid="new-key",
    )

    second = cache.get(
        now=BASE_TIME + timedelta(minutes=2),
        kid="new-key",
    )

    assert first.source == "fetch"
    assert second.source == "cache"
    assert second.reason == "known_kid"
    assert fetcher.calls == 2


def test_expired_cache_refetches():
    fetcher = FakeFetcher(make_jwks("key-1"))
    cache = JwksCache(fetcher)

    cache.get(now=BASE_TIME)

    fetcher.jwks = make_jwks("key-2")

    result = cache.get(
        now=BASE_TIME + DEFAULT_TTL,
    )

    assert result.source == "fetch"
    assert result.reason == "ttl_expired"
    assert result.jwks == make_jwks("key-2")
    assert fetcher.calls == 2


def test_fetch_failure_on_cold_cache_returns_unavailable():
    fetcher = FakeFetcher()
    fetcher.error = RuntimeError("network failure")

    cache = JwksCache(fetcher)

    result = cache.get(now=BASE_TIME)

    assert result.source == "unavailable"
    assert result.reason == "fetch_failed"
    assert result.jwks is None
    assert fetcher.calls == 1


def test_fetch_failure_on_stale_cache_fails_closed():
    fetcher = FakeFetcher(make_jwks("key-1"))
    cache = JwksCache(fetcher)

    first = cache.get(now=BASE_TIME)

    fetcher.error = RuntimeError("network failure")

    result = cache.get(
        now=BASE_TIME + DEFAULT_TTL,
    )

    assert first.source == "fetch"
    assert result.source == "unavailable"
    assert result.reason == "fetch_failed"
    assert result.jwks is None
    assert fetcher.calls == 2


def test_fetcher_recovers_after_failure():
    fetcher = FakeFetcher()
    fetcher.error = RuntimeError("network failure")

    cache = JwksCache(fetcher)

    failed = cache.get(now=BASE_TIME)

    assert failed.source == "unavailable"

    fetcher.error = None
    fetcher.jwks = make_jwks("recovered-key")

    recovered = cache.get(
        now=BASE_TIME + timedelta(seconds=1),
    )

    assert recovered.source == "fetch"
    assert recovered.reason == "cold_cache"
    assert recovered.jwks == make_jwks("recovered-key")
    assert fetcher.calls == 2


@pytest.mark.parametrize(
    "invalid_jwks",
    [
        None,
        {},
        {"keys": "nope"},
        {"keys": []},
        {"keys": [None]},
        {"keys": [{}]},
        {"keys": [{"kid": None}]},
        {"keys": [{"kid": 123}]},
    ],
)
def test_invalid_fetch_result_does_not_poison_cache(invalid_jwks):
    fetcher = FakeFetcher(invalid_jwks)
    cache = JwksCache(fetcher)

    result = cache.get(now=BASE_TIME)

    assert result.source == "unavailable"
    assert result.reason == "invalid_jwks"
    assert result.jwks is None
    assert fetcher.calls == 1


def test_invalid_refresh_does_not_replace_existing_cache():
    fetcher = FakeFetcher(make_jwks("key-1"))
    cache = JwksCache(fetcher)

    first = cache.get(now=BASE_TIME)

    fetcher.jwks = {"keys": "invalid"}

    result = cache.get(
        now=BASE_TIME + timedelta(minutes=1),
        kid="new-key",
    )

    assert first.jwks == make_jwks("key-1")
    assert result.source == "unavailable"
    assert result.reason == "invalid_jwks"

    # A failed refresh must not poison the stored cache.
    fetcher.jwks = make_jwks("key-1")

    recovered = cache.get(
        now=BASE_TIME + timedelta(minutes=2),
        kid="key-1",
    )

    assert recovered.source == "cache"
    assert recovered.reason == "known_kid"
    assert recovered.jwks == make_jwks("key-1")


def test_unknown_kid_does_not_trigger_fetch_before_minimum_interval():
    fetcher = FakeFetcher(make_jwks("key-1"))
    cache = JwksCache(fetcher)

    cache.get(now=BASE_TIME)

    first = cache.get(
        now=BASE_TIME + timedelta(minutes=1),
        kid="unknown-1",
    )

    second = cache.get(
        now=BASE_TIME + timedelta(minutes=1, seconds=1),
        kid="unknown-2",
    )

    third = cache.get(
        now=BASE_TIME + timedelta(minutes=4, seconds=59),
        kid="unknown-3",
    )

    assert first.source == "fetch"
    assert second.source == "cache"
    assert third.source == "cache"
    assert fetcher.calls == 2


def test_unknown_kid_refresh_does_not_happen_for_known_kid():
    fetcher = FakeFetcher(make_jwks("key-1"))
    cache = JwksCache(fetcher)

    cache.get(now=BASE_TIME)

    for minutes in range(1, 100):
        result = cache.get(
            now=BASE_TIME + timedelta(minutes=minutes),
            kid="key-1",
        )

        assert result.source == "cache"

    assert fetcher.calls == 1


def test_no_kid_uses_fresh_cache_without_fetch():
    fetcher = FakeFetcher(make_jwks("key-1"))
    cache = JwksCache(fetcher)

    cache.get(now=BASE_TIME)

    result = cache.get(
        now=BASE_TIME + timedelta(minutes=10),
    )

    assert result.source == "cache"
    assert result.reason == "within_ttl"
    assert fetcher.calls == 1


def test_default_constants_match_spec():
    assert DEFAULT_TTL == timedelta(hours=12)
    assert MIN_REFETCH_INTERVAL == timedelta(minutes=5)


def test_fetcher_is_not_called_for_fresh_known_key():
    calls = []

    def fetcher():
        calls.append("fetch")
        return make_jwks("key-1")

    cache = JwksCache(fetcher)

    cache.get(now=BASE_TIME)

    result = cache.get(
        now=BASE_TIME + timedelta(hours=11, minutes=59),
        kid="key-1",
    )

    assert result.source == "cache"
    assert calls == ["fetch"]


def test_unknown_kid_after_ttl_expiry_uses_ttl_refresh():
    fetcher = FakeFetcher(make_jwks("key-1"))
    cache = JwksCache(fetcher)

    cache.get(now=BASE_TIME)

    fetcher.jwks = make_jwks("key-2")

    result = cache.get(
        now=BASE_TIME + DEFAULT_TTL,
        kid="key-2",
    )

    assert result.source == "fetch"
    assert result.reason == "ttl_expired"
    assert result.jwks == make_jwks("key-2")
    assert fetcher.calls == 2


def test_now_must_be_timezone_aware():
    fetcher = FakeFetcher(make_jwks("key-1"))
    cache = JwksCache(fetcher)

    with pytest.raises(ValueError):
        cache.get(
            now=datetime(2026, 8, 13, 10, 0, 0),
        )


def test_now_must_be_datetime():
    fetcher = FakeFetcher(make_jwks("key-1"))
    cache = JwksCache(fetcher)

    with pytest.raises(TypeError):
        cache.get(now="2026-08-13")


def test_fetcher_must_be_callable():
    with pytest.raises(TypeError):
        JwksCache(None)


def test_negative_ttl_is_rejected():
    fetcher = FakeFetcher(make_jwks("key-1"))

    with pytest.raises(ValueError):
        JwksCache(
            fetcher,
            ttl=timedelta(seconds=-1),
        )


def test_negative_refetch_interval_is_rejected():
    fetcher = FakeFetcher(make_jwks("key-1"))

    with pytest.raises(ValueError):
        JwksCache(
            fetcher,
            min_refetch_interval=timedelta(seconds=-1),
        )


def test_exact_minimum_refetch_interval_allows_refresh():
    fetcher = FakeFetcher(make_jwks("key-1"))
    cache = JwksCache(fetcher)

    cache.get(now=BASE_TIME)

    result = cache.get(
        now=BASE_TIME + MIN_REFETCH_INTERVAL,
        kid="unknown-key",
    )

    assert result.source == "fetch"
    assert result.reason == "unknown_kid"
    assert fetcher.calls == 2