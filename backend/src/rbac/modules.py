from dataclasses import dataclass


BASE_MODULES = frozenset({
    "fcs",
    "nta",
    "tem",
    "western",
})

ADDON_MODULES = frozenset({
    "cross_compare",
    "ai_chat",
})

ALL_MODULES = BASE_MODULES | ADDON_MODULES


@dataclass(frozen=True)
class ModuleResolution:
    granted: list[str]
    rejected: dict[str, str]


def resolve_user_modules(
    license_modules: list[str] | None,
    requested_modules: list[str] | None,
) -> ModuleResolution:
    """
    Resolve which requested modules a user is allowed to receive.

    Rules:
    1. Unknown modules are rejected as "unknown_module".
    2. Known modules not included in the license are rejected as
       "not_in_license".
    3. cross_compare requires at least two granted base modules.
    4. Duplicate module requests are collapsed.
    5. Granted modules are returned in sorted order.
    """

    license_modules = license_modules or []
    requested_modules = requested_modules or []

    granted: set[str] = set()
    rejected: dict[str, str] = {}

    licensed_modules = set(license_modules)

    # Apply rules 1 and 2 first.
    for module in requested_modules:
        if module in granted or module in rejected:
            continue

        if module not in ALL_MODULES:
            rejected[module] = "unknown_module"
            continue

        if module not in licensed_modules:
            rejected[module] = "not_in_license"
            continue

        granted.add(module)

    # Apply the cross_compare dependency only after determining
    # which requested modules actually survived rules 1 and 2.
    if "cross_compare" in granted:
        granted_base_modules = granted & BASE_MODULES

        if len(granted_base_modules) < 2:
            granted.remove("cross_compare")
            rejected["cross_compare"] = "requires_two_base_modules"

    return ModuleResolution(
        granted=sorted(granted),
        rejected=rejected,
    )