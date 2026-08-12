"""
Installer integrity and version checks.

This module contains pure business rules for:
- calculating a file's SHA-256 digest,
- verifying an installer against a trusted digest,
- determining whether the installed version is below a minimum version.

No AWS, network, database, or application infrastructure is used here.
"""

from __future__ import annotations

import hashlib
import hmac
from pathlib import Path


DEFAULT_CHUNK_SIZE = 65_536
SHA256_HEX_LENGTH = 64


def file_sha256(path: str, chunk_size: int = DEFAULT_CHUNK_SIZE) -> str:
    """
    Return the lowercase SHA-256 hexadecimal digest of a file.

    The file is read incrementally instead of being loaded entirely into
    memory. This is important because installers may be very large.

    Args:
        path: Path to the file.
        chunk_size: Number of bytes read per iteration.

    Raises:
        TypeError: If path or chunk_size has the wrong type.
        ValueError: If path is empty or chunk_size is not positive.
        OSError: If the file cannot be opened/read.
    """

    if not isinstance(path, str):
        raise TypeError("path must be a string")

    if not path.strip():
        raise ValueError("path must not be empty")

    # bool is technically an int in Python, but accepting True/False as
    # chunk sizes would be meaningless and is therefore rejected.
    if isinstance(chunk_size, bool) or not isinstance(chunk_size, int):
        raise TypeError("chunk_size must be an integer")

    if chunk_size <= 0:
        raise ValueError("chunk_size must be greater than zero")

    digest = hashlib.sha256()

    with Path(path).open("rb") as file:
        while True:
            chunk = file.read(chunk_size)

            if not chunk:
                break

            digest.update(chunk)

    return digest.hexdigest()


def verify_installer(path: str, expected_sha256: str) -> bool:
    """
    Return True only when the file's SHA-256 digest matches the expected one.

    The comparison uses hmac.compare_digest rather than ordinary equality.
    This is the appropriate constant-time comparison primitive for sensitive
    values and avoids making the comparison itself dependent on how much of
    the digest matched.

    Invalid input, missing files, unreadable files, or an invalid expected
    digest fail closed by returning False.
    """

    if not isinstance(path, str) or not path.strip():
        return False

    if not isinstance(expected_sha256, str):
        return False

    expected = expected_sha256.strip().lower()

    # A SHA-256 hexadecimal digest is exactly 64 hexadecimal characters.
    if len(expected) != SHA256_HEX_LENGTH:
        return False

    try:
        int(expected, 16)
    except ValueError:
        return False

    try:
        actual = file_sha256(path)
    except (OSError, ValueError, TypeError):
        return False

    # Constant-time comparison helps avoid leaking information through
    # timing differences when comparing security-sensitive digest values.
    return hmac.compare_digest(actual, expected)


def needs_forced_update(current: str, minimum: str) -> bool:
    """
    Return True when the current semantic version is below the minimum.

    Versions are compared numerically by dot-separated components, so:

        0.1.9 < 0.1.10

    unlike ordinary string comparison.

    Supported version format:
        MAJOR.MINOR.PATCH

    Optional surrounding whitespace is ignored.

    Raises:
        TypeError: If either version is not a string.
        ValueError: If either version is malformed.
    """

    current_parts = _parse_version(current)
    minimum_parts = _parse_version(minimum)

    return current_parts < minimum_parts


def _parse_version(version: str) -> tuple[int, int, int]:
    """
    Parse a strict MAJOR.MINOR.PATCH semantic version.

    Only the numeric three-component form is accepted because the task
    specifies versions such as "0.1.9" and "0.1.10".
    """

    if not isinstance(version, str):
        raise TypeError("version must be a string")

    value = version.strip()

    if not value:
        raise ValueError("version must not be empty")

    parts = value.split(".")

    if len(parts) != 3:
        raise ValueError("version must have MAJOR.MINOR.PATCH format")

    parsed: list[int] = []

    for part in parts:
        # Reject things such as:
        #   "01"
        #   "+1"
        #   "-1"
        #   "1a"
        # rather than silently interpreting them.
        if not part.isdigit():
            raise ValueError("version components must be non-negative integers")

        if len(part) > 1 and part.startswith("0"):
            raise ValueError("version components must not contain leading zeros")

        parsed.append(int(part))

    return parsed[0], parsed[1], parsed[2]