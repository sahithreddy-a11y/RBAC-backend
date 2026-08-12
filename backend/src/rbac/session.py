from dataclasses import dataclass
from datetime import datetime, timedelta, timezone


ACCESS_TOKEN_LIFETIME = timedelta(hours=1)
REFRESH_TOKEN_LIFETIME = timedelta(days=30)
OFFLINE_GRACE_PERIOD = timedelta(days=7)


@dataclass(frozen=True)
class SessionDecision:
    action: str
    reason: str
    offline_days_remaining: int | None


def _normalize_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None

    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)

    return value.astimezone(timezone.utc)


def evaluate_session(
    access_token_expires_at: datetime | None,
    refresh_token_issued_at: datetime | None,
    last_successful_online_check: datetime | None,
    is_online: bool,
    now: datetime | None = None,
) -> SessionDecision:
    if now is None:
        now = datetime.now(timezone.utc)
    else:
        now = _normalize_datetime(now)

    access_token_expires_at = _normalize_datetime(access_token_expires_at)
    refresh_token_issued_at = _normalize_datetime(refresh_token_issued_at)
    last_successful_online_check = _normalize_datetime(
        last_successful_online_check
    )

    # A valid access token can continue to be used regardless of
    # connectivity.
    if access_token_expires_at is not None and now < access_token_expires_at:
        return SessionDecision(
            action="proceed",
            reason="access_token_valid",
            offline_days_remaining=None,
        )

    # A refresh token older than the allowed lifetime requires a new login.
    if (
        refresh_token_issued_at is not None
        and now - refresh_token_issued_at >= REFRESH_TOKEN_LIFETIME
    ):
        return SessionDecision(
            action="login_required",
            reason="refresh_token_expired",
            offline_days_remaining=None,
        )

    # If the application is online, an expired access token can be refreshed
    # as long as the refresh token is still within its lifetime.
    if is_online:
        if refresh_token_issued_at is not None:
            return SessionDecision(
                action="refresh_required",
                reason="access_token_expired",
                offline_days_remaining=None,
            )

        return SessionDecision(
            action="login_required",
            reason="refresh_token_missing",
            offline_days_remaining=None,
        )

    # Offline access requires a previous successful online check.
    if last_successful_online_check is None:
        return SessionDecision(
            action="login_required",
            reason="no_successful_online_check",
            offline_days_remaining=None,
        )

    # A future online-check timestamp may mean the local clock moved backward
    # or the stored value was tampered with. Do not grant offline grace from
    # untrusted time state; require reconnection instead. A real solution to
    # client clock rollback requires server-side time/state validation.
    if last_successful_online_check > now:
        return SessionDecision(
            action="reconnect_required",
            reason="invalid_future_online_check",
            offline_days_remaining=None,
        )

    elapsed = now - last_successful_online_check

    if elapsed <= OFFLINE_GRACE_PERIOD:
        remaining = OFFLINE_GRACE_PERIOD - elapsed
        remaining_days = remaining.days

        return SessionDecision(
            action="proceed",
            reason="offline_grace_active",
            offline_days_remaining=remaining_days,
        )

    return SessionDecision(
        action="reconnect_required",
        reason="offline_grace_expired",
        offline_days_remaining=0,
    )