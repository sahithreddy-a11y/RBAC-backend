from backend.src.rbac.modules import (
    ALL_MODULES,
    BASE_MODULES,
    ADDON_MODULES,
    resolve_user_modules,
)


def test_module_catalog_contains_expected_modules():
    assert BASE_MODULES == {
        "fcs",
        "nta",
        "tem",
        "western",
    }

    assert ADDON_MODULES == {
        "cross_compare",
        "ai_chat",
    }

    assert ALL_MODULES == BASE_MODULES | ADDON_MODULES


def test_licensed_requested_module_is_granted():
    result = resolve_user_modules(
        ["fcs", "nta"],
        ["fcs"],
    )

    assert result.granted == ["fcs"]
    assert result.rejected == {}


def test_unknown_module_is_rejected():
    result = resolve_user_modules(
        ["fcs", "nta"],
        ["quantum_analysis"],
    )

    assert result.granted == []
    assert result.rejected == {
        "quantum_analysis": "unknown_module"
    }


def test_known_but_unlicensed_module_is_rejected():
    result = resolve_user_modules(
        ["fcs"],
        ["nta"],
    )

    assert result.granted == []
    assert result.rejected == {
        "nta": "not_in_license"
    }


def test_cross_compare_requires_two_granted_base_modules():
    result = resolve_user_modules(
        ["fcs", "cross_compare"],
        ["fcs", "cross_compare"],
    )

    assert result.granted == ["fcs"]
    assert result.rejected == {
        "cross_compare": "requires_two_base_modules"
    }


def test_cross_compare_is_granted_with_two_base_modules():
    result = resolve_user_modules(
        ["fcs", "nta", "cross_compare"],
        ["fcs", "nta", "cross_compare"],
    )

    assert result.granted == [
        "cross_compare",
        "fcs",
        "nta",
    ]
    assert result.rejected == {}


def test_ai_chat_is_granted_when_in_license():
    result = resolve_user_modules(
        ["fcs", "nta", "ai_chat"],
        ["fcs", "ai_chat"],
    )

    assert result.granted == [
        "ai_chat",
        "fcs",
    ]
    assert result.rejected == {}


def test_ai_chat_is_rejected_when_not_in_license():
    result = resolve_user_modules(
        ["fcs", "nta"],
        ["fcs", "ai_chat"],
    )

    assert result.granted == ["fcs"]
    assert result.rejected == {
        "ai_chat": "not_in_license"
    }


def test_duplicate_requests_are_collapsed():
    result = resolve_user_modules(
        ["fcs", "nta"],
        ["fcs", "fcs", "nta", "nta"],
    )

    assert result.granted == ["fcs", "nta"]
    assert result.rejected == {}


def test_granted_modules_are_sorted():
    result = resolve_user_modules(
        ["western", "nta", "fcs"],
        ["western", "nta", "fcs"],
    )

    assert result.granted == [
        "fcs",
        "nta",
        "western",
    ]
    assert result.rejected == {}


def test_unlicensed_base_module_does_not_count_for_cross_compare():
    result = resolve_user_modules(
        ["fcs", "cross_compare"],
        ["fcs", "nta", "cross_compare"],
    )

    assert result.granted == ["fcs"]
    assert result.rejected == {
        "nta": "not_in_license",
        "cross_compare": "requires_two_base_modules",
    }


def test_unknown_module_does_not_count_for_cross_compare():
    result = resolve_user_modules(
        ["fcs", "cross_compare"],
        ["fcs", "quantum_analysis", "cross_compare"],
    )

    assert result.granted == ["fcs"]
    assert result.rejected == {
        "quantum_analysis": "unknown_module",
        "cross_compare": "requires_two_base_modules",
    }


def test_empty_request_returns_empty_resolution():
    result = resolve_user_modules(
        ["fcs", "nta"],
        [],
    )

    assert result.granted == []
    assert result.rejected == {}


def test_empty_license_rejects_known_requested_modules():
    result = resolve_user_modules(
        [],
        ["fcs", "ai_chat"],
    )

    assert result.granted == []
    assert result.rejected == {
        "fcs": "not_in_license",
        "ai_chat": "not_in_license",
    }