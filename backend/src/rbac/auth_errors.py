"""
Authentication error mapping.

This module converts identity-provider exception names into safe,
application-level authentication error information.

Security goals:
- Never expose whether an account exists.
- Never expose internal exception names or implementation details.
- Never raise KeyError for an unknown provider exception.
- Keep user-facing messages safe and actionable.
- Keep logging information useful for internal diagnostics.
"""

from dataclasses import dataclass


# The values below are the only values allowed by the Task 9 contract.
_ALLOWED_ACTIONS = frozenset(
    {
        "retry",
        "reset_password",
        "contact_admin",
        "verify_email",
        "wait_and_retry",
        "none",
    }
)

_ALLOWED_LOG_LEVELS = frozenset(
    {
        "info",
        "warning",
        "error",
    }
)


@dataclass(frozen=True)
class AuthErrorInfo:
    """Safe, immutable representation of an authentication error."""

    user_message: str
    action: str
    retryable: bool
    log_level: str

    def __post_init__(self) -> None:
        """
        Defensively validate the fixed contract.

        The mapper below always creates valid values, but validating the
        dataclass itself prevents accidental construction of invalid
        AuthErrorInfo objects elsewhere in the application.
        """
        if not isinstance(self.user_message, str) or not self.user_message.strip():
            raise ValueError("user_message must be a non-empty string")

        if self.action not in _ALLOWED_ACTIONS:
            raise ValueError(f"Invalid authentication action: {self.action}")

        if not isinstance(self.retryable, bool):
            raise ValueError("retryable must be a boolean")

        if self.log_level not in _ALLOWED_LOG_LEVELS:
            raise ValueError(f"Invalid authentication log level: {self.log_level}")


# ---------------------------------------------------------------------------
# Safe user-facing messages
# ---------------------------------------------------------------------------
#
# These messages deliberately avoid:
# - account existence
# - provider exception names
# - stack traces
# - internal IDs
# - provider-specific implementation details
#
# In particular, WRONG_CREDENTIALS_MESSAGE is shared by
# NotAuthorizedException and UserNotFoundException to prevent
# account enumeration.
# ---------------------------------------------------------------------------

_WRONG_CREDENTIALS_MESSAGE = (
    "We couldn't sign you in with those credentials."
)

_EMAIL_VERIFICATION_MESSAGE = (
    "Please verify your email address before signing in."
)

_PASSWORD_RESET_MESSAGE = (
    "Your password needs to be reset before you can sign in."
)

_RATE_LIMIT_MESSAGE = (
    "Too many attempts. Please wait and try again."
)

_ACCOUNT_UNAVAILABLE_MESSAGE = (
    "This account is currently unavailable. Please contact your administrator."
)

_ACTIVATION_CODE_MESSAGE = (
    "The verification code could not be accepted. Please request a new code "
    "and try again."
)

_INVALID_PASSWORD_MESSAGE = (
    "The password does not meet the required security rules."
)

_GENERIC_MESSAGE = (
    "We couldn't complete the sign-in request. Please try again."
)


def _normalize_exception_name(exception_name) -> str:
    """
    Normalize an exception name safely.

    The public function is typed as accepting str, but authentication
    boundaries should fail closed rather than crashing if malformed input
    reaches the mapper.
    """
    if not isinstance(exception_name, str):
        return ""

    return exception_name.strip()


def _normalize_attempts(attempts) -> int:
    """
    Normalize attempts into a safe non-negative integer.

    The task only requires that attempts be used sensibly. We use it to
    become less willing to immediately retry repeated credential failures.

    bool is deliberately rejected because bool is a subclass of int in
    Python, but True/False are not meaningful attempt counts.
    """
    if isinstance(attempts, bool):
        return 1

    if not isinstance(attempts, int):
        return 1

    return max(1, attempts)


def _credential_error(attempts: int) -> AuthErrorInfo:
    """
    Map credential failures while preventing account enumeration.

    The user-facing message is identical regardless of whether the provider
    reported an incorrect password or a missing account.

    After repeated attempts, we stop encouraging another immediate retry.
    This is an application-level defense against repeated authentication
    attempts. It does not replace provider-side rate limiting.
    """
    if attempts >= 5:
        return AuthErrorInfo(
            user_message=_WRONG_CREDENTIALS_MESSAGE,
            action="wait_and_retry",
            retryable=True,
            log_level="warning",
        )

    return AuthErrorInfo(
        user_message=_WRONG_CREDENTIALS_MESSAGE,
        action="retry",
        retryable=True,
        log_level="info",
    )


def _rate_limit_error(attempts: int) -> AuthErrorInfo:
    """
    Handle provider-side throttling.

    The provider has already indicated that retrying immediately is
    inappropriate. Repeated attempts increase the internal severity,
    while the user receives the same safe message.
    """
    return AuthErrorInfo(
        user_message=_RATE_LIMIT_MESSAGE,
        action="wait_and_retry",
        retryable=True,
        log_level="warning" if attempts < 5 else "error",
    )


def map_auth_error(
    exception_name: str,
    *,
    attempts: int = 1,
) -> AuthErrorInfo:
    """
    Convert an identity-provider exception name into safe auth behavior.

    Unknown or malformed exception names use a safe generic fallback.

    The mapping intentionally distinguishes internal logging information
    from user-facing information. In particular:

        NotAuthorizedException
        UserNotFoundException

    receive the exact same user-facing message so the login endpoint cannot
    be used to enumerate registered accounts.
    """
    normalized_name = _normalize_exception_name(exception_name)
    normalized_attempts = _normalize_attempts(attempts)

    # ------------------------------------------------------------------
    # Credential failures.
    #
    # These MUST share the exact same user-facing message to prevent
    # account enumeration.
    # ------------------------------------------------------------------
    if normalized_name == "NotAuthorizedException":
        return _credential_error(normalized_attempts)

    if normalized_name == "UserNotFoundException":
        result = _credential_error(normalized_attempts)

        # Internally, a missing account is useful information for logs,
        # but it must never be exposed to the user.
        return AuthErrorInfo(
            user_message=result.user_message,
            action=result.action,
            retryable=result.retryable,
            log_level="warning",
        )

    # ------------------------------------------------------------------
    # Email verification.
    # ------------------------------------------------------------------
    if normalized_name == "UserNotConfirmedException":
        return AuthErrorInfo(
            user_message=_EMAIL_VERIFICATION_MESSAGE,
            action="verify_email",
            retryable=False,
            log_level="info",
        )

    # ------------------------------------------------------------------
    # Password reset required.
    # ------------------------------------------------------------------
    if normalized_name == "PasswordResetRequiredException":
        return AuthErrorInfo(
            user_message=_PASSWORD_RESET_MESSAGE,
            action="reset_password",
            retryable=False,
            log_level="info",
        )

    # ------------------------------------------------------------------
    # Provider throttling / rate limiting.
    # ------------------------------------------------------------------
    if normalized_name in {
        "TooManyRequestsException",
        "LimitExceededException",
    }:
        return _rate_limit_error(normalized_attempts)

    # ------------------------------------------------------------------
    # Activation / verification code failures.
    #
    # Both errors intentionally share the same user-facing message so the
    # activation screen does not reveal details about the supplied code.
    # ------------------------------------------------------------------
    if normalized_name == "ExpiredCodeException":
        return AuthErrorInfo(
            user_message=_ACTIVATION_CODE_MESSAGE,
            action="verify_email",
            retryable=False,
            log_level="info",
        )

    if normalized_name == "CodeMismatchException":
        return AuthErrorInfo(
            user_message=_ACTIVATION_CODE_MESSAGE,
            action="verify_email",
            retryable=False,
            log_level="warning",
        )

    # ------------------------------------------------------------------
    # Password policy failure.
    # ------------------------------------------------------------------
    if normalized_name == "InvalidPasswordException":
        return AuthErrorInfo(
            user_message=_INVALID_PASSWORD_MESSAGE,
            action="retry",
            retryable=True,
            log_level="info",
        )

    # ------------------------------------------------------------------
    # Disabled/unavailable account.
    #
    # We do not reveal the exact account state to the user.
    # ------------------------------------------------------------------
    if normalized_name == "UserDisabledException":
        return AuthErrorInfo(
            user_message=_ACCOUNT_UNAVAILABLE_MESSAGE,
            action="contact_admin",
            retryable=False,
            log_level="warning",
        )

    # ------------------------------------------------------------------
    # Unknown provider exception.
    #
    # Never expose the exception name and never let an unknown provider
    # error cause a KeyError.
    # ------------------------------------------------------------------
    return AuthErrorInfo(
        user_message=_GENERIC_MESSAGE,
        action="none",
        retryable=False,
        log_level="error",
    )