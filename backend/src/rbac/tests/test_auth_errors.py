import pytest

from backend.src.rbac.auth_errors import AuthErrorInfo, map_auth_error


def test_not_authorized_and_user_not_found_have_identical_user_message():
    not_authorized = map_auth_error("NotAuthorizedException")
    user_not_found = map_auth_error("UserNotFoundException")

    assert not_authorized.user_message == user_not_found.user_message


def test_not_authorized_and_user_not_found_have_different_log_levels():
    not_authorized = map_auth_error("NotAuthorizedException")
    user_not_found = map_auth_error("UserNotFoundException")

    assert not_authorized.log_level != user_not_found.log_level


def test_not_authorized_is_retryable():
    result = map_auth_error("NotAuthorizedException")

    assert result.retryable is True
    assert result.action == "retry"


def test_repeated_credential_attempts_use_wait_and_retry():
    result = map_auth_error(
        "NotAuthorizedException",
        attempts=5,
    )

    assert result.retryable is True
    assert result.action == "wait_and_retry"


def test_user_not_found_does_not_reveal_account_existence():
    result = map_auth_error("UserNotFoundException")

    forbidden_terms = (
        "not found",
        "does not exist",
        "no such account",
        "UserNotFoundException",
    )

    message = result.user_message.lower()

    assert all(term.lower() not in message for term in forbidden_terms)


def test_user_not_confirmed_requires_email_verification():
    result = map_auth_error("UserNotConfirmedException")

    assert result.action == "verify_email"
    assert result.retryable is False


def test_password_reset_required():
    result = map_auth_error("PasswordResetRequiredException")

    assert result.action == "reset_password"
    assert result.retryable is False


def test_too_many_requests_waits_and_retries():
    result = map_auth_error("TooManyRequestsException")

    assert result.retryable is True
    assert result.action == "wait_and_retry"


def test_limit_exceeded_waits_and_retries():
    result = map_auth_error("LimitExceededException")

    assert result.retryable is True
    assert result.action == "wait_and_retry"


def test_expired_and_mismatched_codes_have_same_user_message():
    expired = map_auth_error("ExpiredCodeException")
    mismatch = map_auth_error("CodeMismatchException")

    assert expired.user_message == mismatch.user_message


def test_expired_code_requires_verification():
    result = map_auth_error("ExpiredCodeException")

    assert result.action == "verify_email"
    assert result.retryable is False


def test_code_mismatch_requires_verification():
    result = map_auth_error("CodeMismatchException")

    assert result.action == "verify_email"
    assert result.retryable is False


def test_invalid_password_is_retryable():
    result = map_auth_error("InvalidPasswordException")

    assert result.action == "retry"
    assert result.retryable is True


def test_user_disabled_contacts_admin():
    result = map_auth_error("UserDisabledException")

    assert result.action == "contact_admin"
    assert result.retryable is False


def test_unknown_exception_uses_safe_fallback():
    result = map_auth_error("SomeCompletelyUnknownException")

    assert result.action == "none"
    assert result.retryable is False
    assert result.log_level == "error"


def test_unknown_exception_does_not_expose_exception_name():
    exception_name = "InternalDatabasePasswordLeakException"

    result = map_auth_error(exception_name)

    assert exception_name not in result.user_message
    assert "exception" not in result.user_message.lower()


def test_unknown_exception_never_raises_key_error():
    result = map_auth_error("SomethingTheProviderHasNeverSeenBefore")

    assert isinstance(result, AuthErrorInfo)


def test_empty_exception_name_uses_safe_fallback():
    result = map_auth_error("")

    assert result.action == "none"
    assert result.retryable is False
    assert result.log_level == "error"


def test_whitespace_exception_name_is_normalized():
    result = map_auth_error("  TooManyRequestsException  ")

    assert result.action == "wait_and_retry"
    assert result.retryable is True


@pytest.mark.parametrize(
    "bad_value",
    [
        None,
        123,
        3.14,
        [],
        {},
        object(),
    ],
)
def test_non_string_exception_name_uses_safe_fallback(bad_value):
    result = map_auth_error(bad_value)

    assert result.action == "none"
    assert result.retryable is False
    assert result.log_level == "error"


@pytest.mark.parametrize(
    "attempts",
    [
        0,
        -1,
        -100,
    ],
)
def test_invalid_attempt_counts_fail_safe(attempts):
    result = map_auth_error(
        "NotAuthorizedException",
        attempts=attempts,
    )

    assert result.action == "retry"
    assert result.retryable is True


def test_boolean_attempt_count_does_not_break_mapping():
    result = map_auth_error(
        "NotAuthorizedException",
        attempts=True,
    )

    assert result.action == "retry"
    assert result.retryable is True


def test_non_integer_attempt_count_does_not_break_mapping():
    result = map_auth_error(
        "NotAuthorizedException",
        attempts="many",
    )

    assert result.action == "retry"
    assert result.retryable is True


def test_large_attempt_count_is_handled_safely():
    result = map_auth_error(
        "NotAuthorizedException",
        attempts=10_000_000,
    )

    assert result.action == "wait_and_retry"
    assert result.retryable is True


def test_auth_error_info_is_immutable():
    result = map_auth_error("NotAuthorizedException")

    with pytest.raises(AttributeError):
        result.action = "contact_admin"


@pytest.mark.parametrize(
    "exception_name",
    [
        "NotAuthorizedException",
        "UserNotFoundException",
        "UserNotConfirmedException",
        "PasswordResetRequiredException",
        "TooManyRequestsException",
        "LimitExceededException",
        "ExpiredCodeException",
        "CodeMismatchException",
        "InvalidPasswordException",
        "UserDisabledException",
        "UnknownException",
    ],
)
def test_all_supported_mappings_have_valid_contract(exception_name):
    result = map_auth_error(exception_name)

    assert isinstance(result.user_message, str)
    assert result.user_message.strip()

    assert result.action in {
        "retry",
        "reset_password",
        "contact_admin",
        "verify_email",
        "wait_and_retry",
        "none",
    }

    assert isinstance(result.retryable, bool)

    assert result.log_level in {
        "info",
        "warning",
        "error",
    }


def test_no_user_message_contains_provider_exception_class_names():
    exception_names = [
        "NotAuthorizedException",
        "UserNotFoundException",
        "UserNotConfirmedException",
        "PasswordResetRequiredException",
        "TooManyRequestsException",
        "LimitExceededException",
        "ExpiredCodeException",
        "CodeMismatchException",
        "InvalidPasswordException",
        "UserDisabledException",
    ]

    for exception_name in exception_names:
        result = map_auth_error(exception_name)

        assert exception_name not in result.user_message


def test_no_user_message_contains_stack_trace_like_information():
    exception_names = [
        "NotAuthorizedException",
        "UserNotFoundException",
        "UserNotConfirmedException",
        "PasswordResetRequiredException",
        "TooManyRequestsException",
        "LimitExceededException",
        "ExpiredCodeException",
        "CodeMismatchException",
        "InvalidPasswordException",
        "UserDisabledException",
        "UnknownException",
    ]

    suspicious_terms = (
        "traceback",
        "stack trace",
        "file ",
        "line ",
        "internal id",
        "request id",
    )

    for exception_name in exception_names:
        result = map_auth_error(exception_name)
        message = result.user_message.lower()

        assert all(term not in message for term in suspicious_terms)