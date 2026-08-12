import hashlib

import pytest

from backend.src.rbac.integrity import (
    file_sha256,
    needs_forced_update,
    verify_installer,
)


# ---------------------------------------------------------------------------
# file_sha256
# ---------------------------------------------------------------------------


def test_file_sha256_returns_correct_digest(tmp_path):
    file_path = tmp_path / "installer.bin"
    content = b"hello integrity"

    file_path.write_bytes(content)

    expected = hashlib.sha256(content).hexdigest()

    assert file_sha256(str(file_path)) == expected


def test_file_sha256_handles_empty_file(tmp_path):
    file_path = tmp_path / "empty.bin"
    file_path.write_bytes(b"")

    expected = hashlib.sha256(b"").hexdigest()

    assert file_sha256(str(file_path)) == expected


def test_file_sha256_reads_file_in_chunks(tmp_path):
    file_path = tmp_path / "large.bin"

    # Larger than the chunk size used by the test.
    content = bytes(range(256)) * 1000
    file_path.write_bytes(content)

    expected = hashlib.sha256(content).hexdigest()

    assert file_sha256(str(file_path), chunk_size=17) == expected


def test_file_sha256_works_when_file_size_is_exact_multiple_of_chunk_size(
    tmp_path,
):
    file_path = tmp_path / "exact.bin"

    content = b"A" * 128
    file_path.write_bytes(content)

    expected = hashlib.sha256(content).hexdigest()

    assert file_sha256(str(file_path), chunk_size=16) == expected


def test_file_sha256_works_when_file_is_smaller_than_chunk_size(tmp_path):
    file_path = tmp_path / "small.bin"

    content = b"small file"
    file_path.write_bytes(content)

    expected = hashlib.sha256(content).hexdigest()

    assert file_sha256(str(file_path), chunk_size=65536) == expected


def test_file_sha256_rejects_non_string_path(tmp_path):
    file_path = tmp_path / "file.bin"
    file_path.write_bytes(b"data")

    with pytest.raises(TypeError):
        file_sha256(file_path)


@pytest.mark.parametrize("path", ["", "   ", "\t", "\n"])
def test_file_sha256_rejects_empty_path(path):
    with pytest.raises(ValueError):
        file_sha256(path)


@pytest.mark.parametrize("chunk_size", [0, -1, -100])
def test_file_sha256_rejects_non_positive_chunk_size(tmp_path, chunk_size):
    file_path = tmp_path / "file.bin"
    file_path.write_bytes(b"data")

    with pytest.raises(ValueError):
        file_sha256(str(file_path), chunk_size=chunk_size)


@pytest.mark.parametrize(
    "chunk_size",
    [True, False, 1.5, "65536", None],
)
def test_file_sha256_rejects_invalid_chunk_size_types(tmp_path, chunk_size):
    file_path = tmp_path / "file.bin"
    file_path.write_bytes(b"data")

    with pytest.raises(TypeError):
        file_sha256(str(file_path), chunk_size=chunk_size)


def test_file_sha256_missing_file_raises_os_error(tmp_path):
    file_path = tmp_path / "does-not-exist.bin"

    with pytest.raises(OSError):
        file_sha256(str(file_path))


# ---------------------------------------------------------------------------
# verify_installer
# ---------------------------------------------------------------------------


def test_verify_installer_accepts_correct_hash(tmp_path):
    file_path = tmp_path / "installer.bin"
    content = b"trusted installer"

    file_path.write_bytes(content)

    expected = hashlib.sha256(content).hexdigest()

    assert verify_installer(str(file_path), expected) is True


def test_verify_installer_rejects_wrong_hash(tmp_path):
    file_path = tmp_path / "installer.bin"
    file_path.write_bytes(b"trusted installer")

    wrong_hash = hashlib.sha256(b"different content").hexdigest()

    assert verify_installer(str(file_path), wrong_hash) is False


def test_verify_installer_accepts_uppercase_hash(tmp_path):
    file_path = tmp_path / "installer.bin"
    content = b"installer"

    file_path.write_bytes(content)

    expected = hashlib.sha256(content).hexdigest().upper()

    assert verify_installer(str(file_path), expected) is True


def test_verify_installer_accepts_hash_with_surrounding_whitespace(tmp_path):
    file_path = tmp_path / "installer.bin"
    content = b"installer"

    file_path.write_bytes(content)

    expected = hashlib.sha256(content).hexdigest()

    assert verify_installer(
        str(file_path),
        f"  {expected}  ",
    ) is True


@pytest.mark.parametrize(
    "expected_hash",
    [
        "",
        " ",
        "abc",
        "0" * 63,
        "0" * 65,
        "z" * 64,
        "g" * 64,
    ],
)
def test_verify_installer_rejects_invalid_sha256(expected_hash, tmp_path):
    file_path = tmp_path / "installer.bin"
    file_path.write_bytes(b"installer")

    assert verify_installer(str(file_path), expected_hash) is False


@pytest.mark.parametrize(
    "path",
    ["", "   ", "\t", "\n"],
)
def test_verify_installer_rejects_empty_path(path):
    assert verify_installer(path, "0" * 64) is False


@pytest.mark.parametrize(
    "expected_hash",
    [
        None,
        123,
        3.14,
        True,
        False,
        b"0" * 64,
    ],
)
def test_verify_installer_rejects_non_string_expected_hash(
    tmp_path,
    expected_hash,
):
    file_path = tmp_path / "installer.bin"
    file_path.write_bytes(b"installer")

    assert verify_installer(str(file_path), expected_hash) is False


def test_verify_installer_missing_file_fails_closed(tmp_path):
    file_path = tmp_path / "missing.bin"

    valid_hash = hashlib.sha256(b"installer").hexdigest()

    assert verify_installer(str(file_path), valid_hash) is False


def test_verify_installer_does_not_raise_for_invalid_path(tmp_path):
    valid_hash = hashlib.sha256(b"installer").hexdigest()

    assert verify_installer(
        str(tmp_path / "missing" / "installer.bin"),
        valid_hash,
    ) is False


def test_verify_installer_detects_file_tampering(tmp_path):
    file_path = tmp_path / "installer.bin"

    original_content = b"original installer"
    file_path.write_bytes(original_content)

    trusted_hash = hashlib.sha256(original_content).hexdigest()

    assert verify_installer(str(file_path), trusted_hash) is True

    file_path.write_bytes(b"modified installer")

    assert verify_installer(str(file_path), trusted_hash) is False


def test_verify_installer_handles_large_file(tmp_path):
    file_path = tmp_path / "large-installer.bin"

    content = bytes(range(256)) * 10000
    file_path.write_bytes(content)

    expected = hashlib.sha256(content).hexdigest()

    assert verify_installer(str(file_path), expected) is True


# ---------------------------------------------------------------------------
# needs_forced_update
# ---------------------------------------------------------------------------


def test_needs_forced_update_when_current_is_below_minimum():
    assert needs_forced_update("0.1.9", "0.1.10") is True


def test_needs_forced_update_when_versions_are_equal():
    assert needs_forced_update("0.1.10", "0.1.10") is False


def test_needs_forced_update_when_current_is_above_minimum():
    assert needs_forced_update("0.1.11", "0.1.10") is False


def test_semantic_version_comparison_does_not_use_string_ordering():
    # String comparison can incorrectly treat 0.1.10 as less than 0.1.9.
    assert needs_forced_update("0.1.9", "0.1.10") is True
    assert needs_forced_update("0.1.10", "0.1.9") is False


@pytest.mark.parametrize(
    "current, minimum, expected",
    [
        ("0.0.0", "0.0.1", True),
        ("0.0.1", "0.0.1", False),
        ("0.1.0", "0.0.9", False),
        ("1.0.0", "0.9.9", False),
        ("1.0.0", "2.0.0", True),
        ("1.2.3", "1.3.0", True),
        ("1.3.0", "1.2.9", False),
        ("2.0.0", "2.0.1", True),
    ],
)
def test_needs_forced_update_compares_major_minor_patch_correctly(
    current,
    minimum,
    expected,
):
    assert needs_forced_update(current, minimum) is expected


@pytest.mark.parametrize(
    "current, minimum",
    [
        (" 0.1.9 ", "0.1.10"),
        ("0.1.9", " 0.1.10 "),
    ],
)
def test_needs_forced_update_ignores_surrounding_whitespace(
    current,
    minimum,
):
    assert needs_forced_update(current, minimum) is True


@pytest.mark.parametrize(
    "version",
    [
        "",
        " ",
        "1",
        "1.2",
        "1.2.3.4",
        "1.2.",
        ".2.3",
        "1..3",
        "1.2.3a",
        "a.2.3",
        "1.a.3",
        "-1.2.3",
        "1.-2.3",
        "1.2.-3",
        "+1.2.3",
        "01.2.3",
        "1.02.3",
        "1.2.03",
    ],
)
def test_needs_forced_update_rejects_malformed_current_version(version):
    with pytest.raises(ValueError):
        needs_forced_update(version, "1.0.0")


@pytest.mark.parametrize(
    "version",
    [
        "",
        " ",
        "1",
        "1.2",
        "1.2.3.4",
        "1.2.",
        ".2.3",
        "1..3",
        "1.2.3a",
        "a.2.3",
        "1.a.3",
        "1.2.-3",
        "+1.2.3",
        "01.2.3",
        "1.02.3",
        "1.2.03",
    ],
)
def test_needs_forced_update_rejects_malformed_minimum_version(version):
    with pytest.raises(ValueError):
        needs_forced_update("1.0.0", version)


@pytest.mark.parametrize(
    "current, minimum",
    [
        (None, "1.0.0"),
        (123, "1.0.0"),
        (1.2, "1.0.0"),
        (True, "1.0.0"),
        ("1.0.0", None),
        ("1.0.0", 123),
        ("1.0.0", 1.2),
        ("1.0.0", False),
    ],
)
def test_needs_forced_update_rejects_non_string_versions(
    current,
    minimum,
):
    with pytest.raises(TypeError):
        needs_forced_update(current, minimum)