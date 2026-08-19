from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any


SCHEMA_VERSION = 2
UNASSIGNED = "__unassigned__"


@dataclass(frozen=True)
class MigrationResult:
    migrated: int
    skipped: int
    failed: int
    errors: list[str]


@dataclass(frozen=True)
class DryRunItem:
    """
    Describe what would happen to one input row.

    action:
      - "migrate": row would be changed by migration
      - "skip": row is already current
      - "fail": row cannot be migrated

    changes contains only fields whose values would change.
    before and after are defensive deep copies.
    """

    index: int
    action: str
    changes: dict[str, Any]
    before: Any
    after: Any
    error: str | None = None


@dataclass(frozen=True)
class DryRunResult:
    """
    Complete report produced by dry-run migration.

    A dry run never modifies the supplied input rows.
    """

    items: list[DryRunItem]
    migrated: int
    skipped: int
    failed: int
    errors: list[str]


def _validate_sample_row(row: Any) -> None:
    """
    Validate the minimum shape required for a Sample migration.

    The real Sample model uses:
      - id: integer primary key
      - user_id: nullable integer
      - sample_id: unique, non-empty string

    user_id=None is valid existing production data and therefore must
    not make a row non-migratable.
    """
    if not isinstance(row, dict):
        raise TypeError("row must be a dict")

    if "sample_id" not in row:
        raise ValueError("row is missing sample_id")

    sample_id = row["sample_id"]

    if not isinstance(sample_id, str):
        raise TypeError("sample_id must be a string")

    if not sample_id.strip():
        raise ValueError("sample_id must not be empty")

    # If present, id must represent the real integer primary key.
    # bool is rejected because bool is a subclass of int in Python.
    if "id" in row:
        row_id = row["id"]

        if (
            isinstance(row_id, bool)
            or not isinstance(row_id, int)
        ):
            raise TypeError("id must be an integer")

        if row_id <= 0:
            raise ValueError("id must be a positive integer")

    # user_id is nullable in the real schema.
    if "user_id" in row and row["user_id"] is not None:
        user_id = row["user_id"]

        if (
            isinstance(user_id, bool)
            or not isinstance(user_id, int)
        ):
            raise TypeError("user_id must be an integer or None")

        if user_id <= 0:
            raise ValueError("user_id must be a positive integer or None")


def _validate_project_id(
    project_id: Any,
    *,
    field_name: str,
) -> None:
    """Validate a project identifier used by migration or reads."""
    if not isinstance(project_id, str):
        raise TypeError(f"{field_name} must be a string")

    if not project_id.strip():
        raise ValueError(f"{field_name} must not be empty")


def _is_valid_project_id(value: Any) -> bool:
    """Return whether a value is a valid non-empty project identifier."""
    return isinstance(value, str) and bool(value.strip())


def _is_current_schema(value: Any) -> bool:
    """
    Return whether a schema version is exactly the supported version.

    bool is intentionally rejected even though bool subclasses int.
    """
    return (
        isinstance(value, int)
        and not isinstance(value, bool)
        and value == SCHEMA_VERSION
    )


def needs_migration(row: dict) -> bool:
    """
    Return True when a row is not fully migrated.

    A row is current only when:
      - project_id exists and is a non-empty string
      - schema_version is exactly SCHEMA_VERSION

    Partially migrated rows therefore remain eligible for migration,
    allowing interrupted backfills to resume safely.
    """
    _validate_sample_row(row)

    return not (
        _is_valid_project_id(row.get("project_id"))
        and _is_current_schema(row.get("schema_version"))
    )


def migrate_row(
    row: dict,
    *,
    default_project_id: str,
) -> dict:
    """
    Return a migrated copy of one Sample row.

    Guarantees:
      - input is never mutated
      - existing valid project_id is preserved
      - missing/empty project_id receives default_project_id
      - schema_version becomes SCHEMA_VERSION
      - future schema versions are rejected
      - user_id=None is preserved
      - extra fields are preserved

    A schema version newer than this migration understands is rejected
    rather than silently downgraded.
    """
    _validate_sample_row(row)

    _validate_project_id(
        default_project_id,
        field_name="default_project_id",
    )

    existing_schema_version = row.get("schema_version")

    if (
        isinstance(existing_schema_version, int)
        and not isinstance(existing_schema_version, bool)
        and existing_schema_version > SCHEMA_VERSION
    ):
        raise ValueError(
            "row schema_version is newer than the supported schema"
        )

    migrated = dict(row)

    existing_project_id = row.get("project_id")

    if _is_valid_project_id(existing_project_id):
        # Existing ownership is authoritative.
        migrated["project_id"] = existing_project_id
    else:
        migrated["project_id"] = default_project_id

    migrated["schema_version"] = SCHEMA_VERSION

    return migrated


def _calculate_changes(
    before: dict,
    after: dict,
) -> dict[str, Any]:
    """
    Return only fields whose values differ between two rows.

    Deep copies are returned so callers cannot mutate either the
    original input or the migration result through the report.
    """
    changes: dict[str, Any] = {}

    all_keys = set(before) | set(after)

    for key in all_keys:
        before_value = before.get(key)
        after_value = after.get(key)

        if before_value != after_value:
            changes[key] = {
                "before": copy.deepcopy(before_value)
                if key in before
                else None,
                "after": copy.deepcopy(after_value)
                if key in after
                else None,
            }

    return changes


def migrate_rows(
    rows: list[dict],
    *,
    default_project_id: str,
    batch_size: int = 500,
) -> tuple[list[dict], MigrationResult]:
    """
    Safely migrate a snapshot of Sample rows.

    Important concurrency property:
        `rows` represents the rows observed by this invocation.

    Rows inserted into the database after this snapshot was obtained
    are not silently assumed to have been migrated. A later pass over
    the newly observed rows is required.

    Guarantees:
      - input list is never mutated
      - input dictionaries are never mutated
      - one malformed row does not stop the batch
      - already-migrated rows are skipped
      - partially migrated rows can resume
      - existing project assignments are preserved
      - future schema versions fail closed
      - batch_size affects processing boundaries, not semantics
    """
    if not isinstance(rows, list):
        raise TypeError("rows must be a list")

    _validate_project_id(
        default_project_id,
        field_name="default_project_id",
    )

    if (
        isinstance(batch_size, bool)
        or not isinstance(batch_size, int)
        or batch_size <= 0
    ):
        raise ValueError("batch_size must be a positive integer")

    result: list[dict] = []

    migrated_count = 0
    skipped_count = 0
    failed_count = 0
    errors: list[str] = []

    for batch_start in range(0, len(rows), batch_size):
        batch = rows[
            batch_start : batch_start + batch_size
        ]

        for offset, row in enumerate(batch):
            index = batch_start + offset

            try:
                if needs_migration(row):
                    migrated_row = migrate_row(
                        row,
                        default_project_id=default_project_id,
                    )

                    result.append(migrated_row)
                    migrated_count += 1

                else:
                    # Return a shallow copy so the caller cannot mutate
                    # the original row through the returned collection.
                    result.append(dict(row))
                    skipped_count += 1

            except (TypeError, ValueError, KeyError) as exc:
                failed_count += 1

                errors.append(
                    f"row[{index}]: "
                    f"{type(exc).__name__}: {exc}"
                )

                # Preserve the original value in a copied form when
                # possible. This allows a caller to identify and retry
                # failed rows without data loss.
                if isinstance(row, dict):
                    result.append(dict(row))
                else:
                    result.append(row)

            except Exception as exc:
                # Defensive record-level boundary. A single unexpected
                # failure must not terminate a potentially large
                # migration batch.
                failed_count += 1

                errors.append(
                    f"row[{index}]: "
                    f"{type(exc).__name__}: {exc}"
                )

                if isinstance(row, dict):
                    result.append(dict(row))
                else:
                    result.append(row)

    return result, MigrationResult(
        migrated=migrated_count,
        skipped=skipped_count,
        failed=failed_count,
        errors=errors,
    )


def dry_run_migrate_rows(
    rows: list[dict],
    *,
    default_project_id: str,
    batch_size: int = 500,
) -> DryRunResult:
    """
    Report what migrate_rows() would do without modifying anything.

    The dry-run intentionally reuses:
      - needs_migration()
      - migrate_row()

    Therefore the decision-making and validation rules remain identical
    to the real migration.

    Guarantees:
      - input list is never mutated
      - input dictionaries are never mutated
      - nested input values are never mutated
      - no migration is committed
      - every input row receives exactly one report item
      - already-current rows are reported as "skip"
      - migratable rows are reported as "migrate"
      - malformed/future-schema rows are reported as "fail"
      - one bad row does not stop the report
      - batch_size affects processing boundaries, not semantics
      - repeated dry-runs produce equivalent reports
      - returned report data is defensively copied
    """
    if not isinstance(rows, list):
        raise TypeError("rows must be a list")

    _validate_project_id(
        default_project_id,
        field_name="default_project_id",
    )

    if (
        isinstance(batch_size, bool)
        or not isinstance(batch_size, int)
        or batch_size <= 0
    ):
        raise ValueError("batch_size must be a positive integer")

    items: list[DryRunItem] = []

    migrated_count = 0
    skipped_count = 0
    failed_count = 0
    errors: list[str] = []

    for batch_start in range(0, len(rows), batch_size):
        batch = rows[
            batch_start : batch_start + batch_size
        ]

        for offset, row in enumerate(batch):
            index = batch_start + offset

            try:
                if needs_migration(row):
                    proposed = migrate_row(
                        row,
                        default_project_id=default_project_id,
                    )

                    changes = _calculate_changes(
                        row,
                        proposed,
                    )

                    items.append(
                        DryRunItem(
                            index=index,
                            action="migrate",
                            changes=copy.deepcopy(changes),
                            before=copy.deepcopy(row),
                            after=copy.deepcopy(proposed),
                        )
                    )

                    migrated_count += 1

                else:
                    current = copy.deepcopy(row)

                    items.append(
                        DryRunItem(
                            index=index,
                            action="skip",
                            changes={},
                            before=copy.deepcopy(row),
                            after=current,
                        )
                    )

                    skipped_count += 1

            except (TypeError, ValueError, KeyError) as exc:
                error = (
                    f"row[{index}]: "
                    f"{type(exc).__name__}: {exc}"
                )

                errors.append(error)
                failed_count += 1

                items.append(
                    DryRunItem(
                        index=index,
                        action="fail",
                        changes={},
                        before=copy.deepcopy(row),
                        after=copy.deepcopy(row),
                        error=error,
                    )
                )

            except Exception as exc:
                error = (
                    f"row[{index}]: "
                    f"{type(exc).__name__}: {exc}"
                )

                errors.append(error)
                failed_count += 1

                items.append(
                    DryRunItem(
                        index=index,
                        action="fail",
                        changes={},
                        before=copy.deepcopy(row),
                        after=copy.deepcopy(row),
                        error=error,
                    )
                )

    return DryRunResult(
        items=items,
        migrated=migrated_count,
        skipped=skipped_count,
        failed=failed_count,
        errors=errors,
    )


def scoped_sample_filter(
    rows: list[dict],
    *,
    project_id: str,
    include_unassigned: bool = True,
) -> list[dict]:
    """
    Return samples visible to a project during the migration window.

    Migration-window policy:
      - A valid project_id is strictly matched.
      - Missing, empty, or invalid project_id means UNASSIGNED.
      - By default, unassigned rows remain visible so that users do not
        interpret an incomplete backfill as data loss.
      - include_unassigned=False enables strict project-only filtering.
      - A requested project_id of UNASSIGNED explicitly returns
        unassigned rows.

    Malformed non-dict entries are ignored because this is a read path;
    one bad entry should not hide otherwise valid samples.

    Returned dictionaries are copies. The input is never mutated.
    """
    if not isinstance(rows, list):
        raise TypeError("rows must be a list")

    _validate_project_id(
        project_id,
        field_name="project_id",
    )

    if not isinstance(include_unassigned, bool):
        raise TypeError(
            "include_unassigned must be a boolean"
        )

    scoped: list[dict] = []

    for row in rows:
        if not isinstance(row, dict):
            continue

        actual_project_id = row.get("project_id")

        if _is_valid_project_id(actual_project_id):
            if actual_project_id == project_id:
                scoped.append(dict(row))

            continue

        # Missing/empty/invalid project_id is treated as unassigned.
        if include_unassigned:
            scoped.append(dict(row))

    return scoped