import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone


TOKEN_PREFIX = "BV-"
TOKEN_BODY_LENGTH = 6
TOKEN_TTL_HOURS = 48

# Exclude visually ambiguous characters such as I, L, O, 0, and 1
# because the token is intended to be read and typed by a person.
TOKEN_CHARACTERS = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"

# secrets is used instead of random because activation tokens grant access
# and must be difficult to predict.
def generate_activation_token() -> str:
    """Return a new activation token, e.g. 'BV-X7K2MP'."""
    body = "".join(
        secrets.choice(TOKEN_CHARACTERS)
        for _ in range(TOKEN_BODY_LENGTH)
    )
    return TOKEN_PREFIX + body


def is_valid_token_format(token: str) -> bool:
    """
    Return True only when token has the exact BV-XXXXXX format.

    Lowercase input is rejected because generated activation tokens are
    uppercase and the format is intentionally case-sensitive.
    """
    if not isinstance(token, str):
        return False

    if not token.startswith(TOKEN_PREFIX):
        return False

    body = token[len(TOKEN_PREFIX):]

    if len(body) != TOKEN_BODY_LENGTH:
        return False

    return all(character in TOKEN_CHARACTERS for character in body)


def token_expiry_from(created_at: datetime) -> str:
    """Return the ISO 8601 UTC expiry timestamp for a created token."""
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)

    expiry = created_at + timedelta(hours=TOKEN_TTL_HOURS)

    return expiry.astimezone(timezone.utc).isoformat()


@dataclass(frozen=True)
class TokenCheck:
    valid: bool
    reason: str


def check_activation_token(
    record: dict | None,
    now: datetime | None = None,
) -> TokenCheck:
    """Decide whether a stored activation token may be redeemed."""
    if record is None:
        return TokenCheck(False, "not_found")

    token = record.get("token")

    if not is_valid_token_format(token):
        return TokenCheck(False, "malformed")

    if record.get("used") is True:
        return TokenCheck(False, "already_used")

    expires_at = record.get("expires_at")

    if not isinstance(expires_at, str):
        return TokenCheck(False, "malformed")

    try:
        expiry = datetime.fromisoformat(expires_at)
    except ValueError:
        return TokenCheck(False, "malformed")

    if expiry.tzinfo is None:
        expiry = expiry.replace(tzinfo=timezone.utc)

    if now is None:
        now = datetime.now(timezone.utc)
    elif now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    now = now.astimezone(timezone.utc)
    expiry = expiry.astimezone(timezone.utc)

    if now >= expiry:
        return TokenCheck(False, "expired")

    return TokenCheck(True, "ok")