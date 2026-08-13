from dataclasses import dataclass
from datetime import datetime

from backend.src.rbac.claims import parse_claims
from backend.src.rbac.license_status import evaluate_license
from backend.src.rbac.modules import resolve_user_modules


@dataclass(frozen=True)
class TokenClaims:
    claims: dict[str, str]
    warnings: list[str]


def _string_or_empty(value) -> str:
    if isinstance(value, str):
        return value.strip()
    return ""


def _get_license(organization: dict):
    if not isinstance(organization, dict):
        return None

    license_data = organization.get("license")

    if isinstance(license_data, dict):
        return license_data

    return None


def _get_requested_modules(user: dict) -> list[str]:
    if not isinstance(user, dict):
        return []

    value = user.get("requested_modules")

    if value is None:
        value = user.get("modules")

    if isinstance(value, str):
        return [
            item.strip()
            for item in value.split(",")
            if item.strip()
        ]

    if isinstance(value, (list, tuple)):
        return [
            item.strip()
            for item in value
            if isinstance(item, str) and item.strip()
        ]

    return []


def _get_license_modules(license_data: dict) -> list[str]:
    if not isinstance(license_data, dict):
        return []

    value = license_data.get("modules")

    if isinstance(value, str):
        return [
            item.strip()
            for item in value.split(",")
            if item.strip()
        ]

    if isinstance(value, (list, tuple)):
        return [
            item.strip()
            for item in value
            if isinstance(item, str) and item.strip()
        ]

    return []


def build_token_claims(
    *,
    user: dict,
    organization: dict,
    now: datetime,
) -> TokenClaims:
    """
    Build string-only claims for token generation.

    This function deliberately computes module entitlements at token
    issuance time instead of copying a previously stored entitlement list.
    """

    warnings: list[str] = []

    # Fail closed for malformed top-level input.
    if not isinstance(user, dict):
        return TokenClaims(
            claims={
                "sub": "",
                "email": "",
                "org_id": "",
                "role": "",
                "modules": "",
                "license_id": "",
                "license_type": "",
                "license_expires": "",
                "license_status": "",
            },
            warnings=["invalid_user"],
        )

    if not isinstance(organization, dict):
        return TokenClaims(
            claims={
                "sub": _string_or_empty(user.get("sub")),
                "email": _string_or_empty(user.get("email")),
                "org_id": "",
                "role": _string_or_empty(user.get("role")) or "researcher",
                "modules": "",
                "license_id": "",
                "license_type": "",
                "license_expires": "",
                "license_status": "",
            },
            warnings=["missing_or_invalid_organization"],
        )

    if not isinstance(now, datetime):
        return TokenClaims(
            claims={
                "sub": _string_or_empty(user.get("sub")),
                "email": _string_or_empty(user.get("email")),
                "org_id": "",
                "role": _string_or_empty(user.get("role")) or "researcher",
                "modules": "",
                "license_id": "",
                "license_type": "",
                "license_expires": "",
                "license_status": "",
            },
            warnings=["invalid_now"],
        )

    license_data = _get_license(organization)

    if not isinstance(license_data, dict):
        license_data = {}
        warnings.append("missing_license_record")

    org_id = organization.get("org_id")

    if not isinstance(org_id, str) or not org_id.strip():
        warnings.append("missing_organization_id")
        org_id_value = ""
    else:
        org_id_value = org_id.strip()

    license_id = _string_or_empty(
        license_data.get("license_id", license_data.get("id"))
    )
    license_type = _string_or_empty(license_data.get("license_type", license_data.get("type")))
    license_expires = _string_or_empty(
        license_data.get("license_expires", license_data.get("expires"))
    )
    license_status = _string_or_empty(
        license_data.get("license_status", license_data.get("status"))
    ) or "active"

    requested_modules = _get_requested_modules(user)
    licensed_modules = _get_license_modules(license_data)

    # Warn about suspicious requested modules before resolution.
    for module in requested_modules:
        if module not in licensed_modules:
            warnings.append(
                f"module_not_in_license:{module}"
            )

    # Evaluate the license using the injected clock.
    status_result = evaluate_license(
        license_status,
        license_expires or None,
        now=now,
    )

    if not status_result.valid:
        modules_value = ""
    else:
        resolution = resolve_user_modules(
            licensed_modules,
            requested_modules,
        )
        modules_value = ",".join(resolution.granted)

        for module, reason in resolution.rejected.items():
            if reason == "not_in_license":
                warning = f"module_not_in_license:{module}"
            else:
                warning = f"module_rejected:{module}:{reason}"

            if warning not in warnings:
                warnings.append(warning)

    claims = {
        "sub": _string_or_empty(user.get("sub")),
        "email": _string_or_empty(user.get("email")),
        "org_id": org_id_value,
        "role": _string_or_empty(user.get("role")) or "researcher",
        "modules": modules_value,
        "license_id": license_id,
        "license_type": license_type,
        "license_expires": license_expires,
        "license_status": license_status,
    }

    # External token contract: every emitted claim MUST be a string.
    assert all(isinstance(value, str) for value in claims.values())

    return TokenClaims(
        claims=claims,
        warnings=warnings,
    )