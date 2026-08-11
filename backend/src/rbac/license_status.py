from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone


WARNING_THRESHOLD_DAYS = 30


@dataclass(frozen=True)
class LicenseStatus:
    valid: bool
    expired: bool
    days_remaining: int | None
    show_warning: bool
    reason: str


def evaluate_license(
    status: str,
    expires_at: str | None,
    now: datetime | None = None,
) -> LicenseStatus:
    """
    Evaluate the current license status.

    A non-active license is never valid. A perpetual or missing expiry
    never expires. Date-based licenses are valid while their expiry
    instant is still in the future.

    Date-only expiry values are treated as valid through that calendar
    day. Full ISO timestamps are compared using their exact time.
    """

    if status == "revoked":
        return LicenseStatus(
            valid=False,
            expired=False,
            days_remaining=None,
            show_warning=False,
            reason="revoked",
        )

    if status == "suspended":
        return LicenseStatus(
            valid=False,
            expired=False,
            days_remaining=None,
            show_warning=False,
            reason="suspended",
        )

    if status == "expired":
        return LicenseStatus(
            valid=False,
            expired=True,
            days_remaining=None,
            show_warning=False,
            reason="expired",
        )

    if status != "active":
        # The document defines status as active, expired, revoked,
        # or suspended. Unexpected status values fail closed.
        return LicenseStatus(
            valid=False,
            expired=False,
            days_remaining=None,
            show_warning=False,
            reason="invalid_date",
        )

    if expires_at is None or expires_at == "perpetual":
        return LicenseStatus(
            valid=True,
            expired=False,
            days_remaining=None,
            show_warning=False,
            reason="perpetual",
        )

    if not isinstance(expires_at, str):
        return LicenseStatus(
            valid=False,
            expired=False,
            days_remaining=None,
            show_warning=False,
            reason="invalid_date",
        )

    if now is None:
        now = datetime.now(timezone.utc)
    elif now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    now = now.astimezone(timezone.utc)

    try:
        parsed_date = date.fromisoformat(expires_at)

        # Date-only values expire at the beginning of the next day,
        # so the entire stated expiry date remains valid.
        expiry = datetime.combine(
            parsed_date + timedelta(days=1),
            time.min,
            tzinfo=timezone.utc,
        )
    except ValueError:
        try:
            expiry = datetime.fromisoformat(expires_at)

            if expiry.tzinfo is None:
                expiry = expiry.replace(tzinfo=timezone.utc)

            expiry = expiry.astimezone(timezone.utc)
        except ValueError:
            return LicenseStatus(
                valid=False,
                expired=False,
                days_remaining=None,
                show_warning=False,
                reason="invalid_date",
            )

    if expiry <= now:
        return LicenseStatus(
            valid=False,
            expired=True,
            days_remaining=0,
            show_warning=False,
            reason="expired",
        )

    remaining_seconds = (expiry - now).total_seconds()
    days_remaining = int(remaining_seconds // 86400)

    return LicenseStatus(
        valid=True,
        expired=False,
        days_remaining=days_remaining,
        show_warning=days_remaining < WARNING_THRESHOLD_DAYS,
        reason="ok",
    )