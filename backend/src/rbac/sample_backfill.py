from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass

from rbac.migration import (
    MigrationResult,
    migrate_row,
    needs_migration,
)


CHECKPOINT_KIND = "sample_backfill"
CHECKPOINT_VERSION = 1


@dataclass(frozen=True)
class BackfillPlan:
    to_migrate: int
    already_current: int
    unmigratable: int
    warnings: list[str]


def _valid_sample_id(row: dict) -> str | None:
    value = row.get("sample_id")

    if isinstance(value, str) and value.strip():
        return value

    return None


def _snapshot_fingerprint(rows: list[dict]) -> str:
    """
    Create a deterministic fingerprint from stable sample identities.

    The fingerprint deliberately ignores row order because production rows
    may be returned in different orders between reads.
    """
    sample_ids = sorted(
        sample_id
        for row in rows
        if isinstance(row, dict)
        for sample_id in [_valid_sample_id(row)]
        if sample_id is not None
    )

    payload = json.dumps(
        sample_ids,
        separators=(",", ":"),
        ensure_ascii=True,
    )

    return hashlib.sha256(
        payload.encode("utf-8")
    ).hexdigest()


def _validate_checkpoint(
    checkpoint: dict,
    rows: list[dict],
) -> set[str]:
    if not isinstance(checkpoint, dict):
        raise TypeError("checkpoint must be a dict or None")

    if checkpoint.get("kind") != CHECKPOINT_KIND:
        raise ValueError(
            "checkpoint is for a different backfill"
        )

    if checkpoint.get("version") != CHECKPOINT_VERSION:
        raise ValueError(
            "unsupported checkpoint version"
        )

    processed = checkpoint.get("processed_sample_ids")

    if not isinstance(processed, list):
        raise ValueError(
            "checkpoint has invalid processed_sample_ids"
        )

    if not all(
        isinstance(sample_id, str)
        and sample_id.strip()
        for sample_id in processed
    ):
        raise ValueError(
            "checkpoint has invalid processed_sample_ids"
        )

    if len(processed) != len(set(processed)):
        raise ValueError(
            "checkpoint contains duplicate sample_ids"
        )

    fingerprint = checkpoint.get("snapshot_fingerprint")

    if (
        not isinstance(fingerprint, str)
        or len(fingerprint) != 64
    ):
        raise ValueError(
            "checkpoint has invalid snapshot_fingerprint"
        )

    current_ids = {
        sample_id
        for row in rows
        if isinstance(row, dict)
        for sample_id in [_valid_sample_id(row)]
        if sample_id is not None
    }

    processed_ids = set(processed)

    # A legitimate later snapshot may contain newly inserted rows, so we do
    # not require the fingerprints to be identical.
    #
    # But if none of the checkpoint's processed identities exist anymore,
    # treating it as a valid checkpoint would be dangerous.
    if processed_ids and not (
        processed_ids & current_ids
    ):
        raise ValueError(
            "checkpoint does not match the supplied rows"
        )

    return processed_ids


def plan_backfill(
    rows: list[dict],
) -> BackfillPlan:
    """
    Inspect production rows without modifying them.

    Counts:
      - to_migrate: rows that Task 22 says need migration
      - already_current: rows already on the current schema
      - unmigratable: malformed rows that cannot safely be migrated

    Legacy values generate warnings but do not themselves make a row
    unmigratable.
    """
    if not isinstance(rows, list):
        raise TypeError("rows must be a list")

    to_migrate = 0
    already_current = 0
    unmigratable = 0
    warnings: list[str] = []

    for index, row in enumerate(rows):
        try:
            if not isinstance(row, dict):
                raise TypeError("row must be a dict")

            if needs_migration(row):
                to_migrate += 1
            else:
                already_current += 1

            if row.get("treatment") == "Unknown":
                warnings.append(
                    f"row[{index}]: "
                    "treatment 'Unknown' will be normalized to None"
                )

            if row.get("user_id") is None:
                warnings.append(
                    f"row[{index}]: "
                    "user_id is NULL; ownership may change before "
                    "a later pass"
                )

        except (TypeError, ValueError, KeyError) as exc:
            unmigratable += 1
            warnings.append(
                f"row[{index}]: "
                f"{type(exc).__name__}: {exc}"
            )

    return BackfillPlan(
        to_migrate=to_migrate,
        already_current=already_current,
        unmigratable=unmigratable,
        warnings=warnings,
    )


def normalize_legacy_values(
    row: dict,
) -> dict:
    """
    Normalize legacy representations without modifying the input.

    'Unknown' means the treatment was not recorded, so it is normalized
    to None. This makes legacy 'Unknown' equivalent to newer NULL data.
    """
    if not isinstance(row, dict):
        raise TypeError("row must be a dict")

    normalized = copy.deepcopy(row)

    if normalized.get("treatment") == "Unknown":
        normalized["treatment"] = None

    return normalized


def _build_checkpoint(
    processed_sample_ids: set[str],
    snapshot_fingerprint: str,
) -> dict:
    return {
        "kind": CHECKPOINT_KIND,
        "version": CHECKPOINT_VERSION,
        "snapshot_fingerprint": snapshot_fingerprint,
        "processed_sample_ids": sorted(
            processed_sample_ids
        ),
    }


def run_backfill(
    rows: list[dict],
    *,
    default_project_id: str,
    batch_size: int = 500,
    checkpoint: dict | None = None,
) -> tuple[list[dict], MigrationResult, dict]:
    """
    Process one resumable batch of production rows.

    sample_id is used as the stable checkpoint identity rather than a
    positional row index.

    Rows inserted after an earlier pass have new sample_ids and are therefore
    picked up automatically on the next pass.

    A row whose ownership changed since an earlier pass is evaluated using
    its current values. Task 22's migrate_row() preserves an existing valid
    project_id, so a backfill never overwrites real ownership with the
    default project.
    """
    if not isinstance(rows, list):
        raise TypeError("rows must be a list")

    if (
        isinstance(batch_size, bool)
        or not isinstance(batch_size, int)
        or batch_size <= 0
    ):
        raise ValueError(
            "batch_size must be a positive integer"
        )

    if checkpoint is None:
        processed_ids: set[str] = set()
        snapshot_fingerprint = _snapshot_fingerprint(
            rows
        )
    else:
        processed_ids = _validate_checkpoint(
            checkpoint,
            rows,
        )

        snapshot_fingerprint = checkpoint[
            "snapshot_fingerprint"
        ]

    result_rows = copy.deepcopy(rows)

    candidates: list[
        tuple[str, int, dict]
    ] = []

    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            continue

        sample_id = _valid_sample_id(row)

        if sample_id is None:
            continue

        candidates.append(
            (
                sample_id,
                index,
                row,
            )
        )

    # Stable ordering makes the checkpointed run deterministic.
    candidates.sort(
        key=lambda item: item[0]
    )

    migrated_count = 0
    skipped_count = 0
    failed_count = 0
    errors: list[str] = []

    processed_this_run = 0

    for sample_id, index, row in candidates:

        if sample_id in processed_ids:
            continue

        if processed_this_run >= batch_size:
            break

        try:
            normalized = normalize_legacy_values(
                row
            )

            migrated_row = migrate_row(
                normalized,
                default_project_id=default_project_id,
            )

            result_rows[index] = migrated_row

            if (
                needs_migration(row)
                or normalized != row
            ):
                migrated_count += 1
            else:
                skipped_count += 1

            processed_ids.add(sample_id)
            processed_this_run += 1

        except Exception as exc:
            failed_count += 1
            processed_this_run += 1

            errors.append(
                f"row[{index}]: "
                f"{type(exc).__name__}: {exc}"
            )

            # Do NOT mark a failed row as processed.
            # It must be eligible for repair and retry.
            result_rows[index] = copy.deepcopy(row)

    checkpoint_out = _build_checkpoint(
        processed_ids,
        snapshot_fingerprint,
    )

    return (
        result_rows,
        MigrationResult(
            migrated=migrated_count,
            skipped=skipped_count,
            failed=failed_count,
            errors=errors,
        ),
        checkpoint_out,
    )