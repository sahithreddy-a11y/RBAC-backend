from __future__ import annotations

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


def _validate_record(record: Any) -> None:
    """
    Validate the minimum shape required for migration.

    A record must be a dictionary containing a non-empty string
    sample_id and org_id.

    Migration must reject malformed records rather than silently
    producing partially valid records.
    """
    if not isinstance(record, dict):
        raise TypeError("record must be a dict")

    if "sample_id" not in record:
        raise ValueError("record is missing sample_id")

    if not isinstance(record["sample_id"], str):
        raise TypeError("sample_id must be a string")

    if not record["sample_id"].strip():
        raise ValueError("sample_id must not be empty")

    if "org_id" not in record:
        raise ValueError("record is missing org_id")

    if not isinstance(record["org_id"], str):
        raise TypeError("org_id must be a string")

    if not record["org_id"].strip():
        raise ValueError("org_id must not be empty")


def _validate_project_id(project_id: Any, *, field_name: str) -> None:
    """
    Validate project identifiers used by migration and reads.
    """
    if not isinstance(project_id, str):
        raise TypeError(f"{field_name} must be a string")

    if not project_id.strip():
        raise ValueError(f"{field_name} must not be empty")


def needs_migration(record: dict) -> bool:
    """
    Return True when a record is not yet at the current schema.

    A record is considered migrated only when both:
      - project_id exists and is a non-empty string
      - schema_version == SCHEMA_VERSION

    This deliberately treats partially migrated records as needing
    migration. That allows an interrupted migration to safely resume.
    """
    _validate_record(record)

    project_id = record.get("project_id")
    schema_version = record.get("schema_version")

    if (
        isinstance(project_id, str)
        and project_id.strip()
        and schema_version == SCHEMA_VERSION
    ):
        return False

    return True


def migrate_record(
    record: dict,
    *,
    default_project_id: str,
) -> dict:
    """
    Return a migrated copy of one record.

    Migration is idempotent:
      - an already migrated record is returned unchanged
      - an existing valid project_id is preserved
      - schema_version is brought to SCHEMA_VERSION
      - missing project_id receives default_project_id

    The input record is never mutated.

    A future schema version is rejected rather than silently downgraded.
    """
    _validate_record(record)
    _validate_project_id(
        default_project_id,
        field_name="default_project_id",
    )

    existing_schema_version = record.get("schema_version")

    if (
        isinstance(existing_schema_version, int)
        and not isinstance(existing_schema_version, bool)
        and existing_schema_version > SCHEMA_VERSION
    ):
        raise ValueError(
            "record schema_version is newer than the supported schema"
        )

    # Always create a new dictionary.
    migrated = dict(record)

    existing_project_id = record.get("project_id")

    if (
        isinstance(existing_project_id, str)
        and existing_project_id.strip()
    ):
        # Preserve an existing project assignment.
        migrated["project_id"] = existing_project_id
    else:
        # Missing/empty project_id is treated as unassigned.
        migrated["project_id"] = default_project_id

    migrated["schema_version"] = SCHEMA_VERSION

    return migrated


def migrate_batch(
    records: list[dict],
    *,
    default_project_id: str,
    batch_size: int = 100,
) -> tuple[list[dict], MigrationResult]:
    """
    Migrate a collection of records safely.

    Properties:
      - input list is never mutated
      - individual records are never mutated
      - one malformed record does not stop the batch
      - already-migrated records are skipped
      - partially migrated records can be retried
      - batch_size controls processing boundaries but not results
      - errors contain record position and reason
    """
    if not isinstance(records, list):
        raise TypeError("records must be a list")

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

    # Process in explicit batches so the implementation remains safe
    # when this in-memory representation is later replaced by a database
    # cursor/page based implementation.
    for batch_start in range(0, len(records), batch_size):
        batch = records[batch_start : batch_start + batch_size]

        for offset, record in enumerate(batch):
            index = batch_start + offset

            try:
                if needs_migration(record):
                    migrated_record = migrate_record(
                        record,
                        default_project_id=default_project_id,
                    )
                    result.append(migrated_record)
                    migrated_count += 1
                else:
                    # Return a copy even for skipped records so callers
                    # cannot accidentally mutate the original input list.
                    result.append(dict(record))
                    skipped_count += 1

            except (TypeError, ValueError, KeyError) as exc:
                failed_count += 1

                errors.append(
                    f"record[{index}]: {type(exc).__name__}: {exc}"
                )

                # Preserve the original record in the output as a copy.
                # This allows callers to identify/retry the failed record
                # without losing data from the migration result.
                if isinstance(record, dict):
                    result.append(dict(record))
                else:
                    # The declared API accepts list[dict], but malformed
                    # runtime input should still not terminate the batch.
                    result.append(record)

            except Exception as exc:
                # Defensive boundary: an unexpected record-level failure
                # must not terminate a potentially large migration.
                failed_count += 1

                errors.append(
                    f"record[{index}]: "
                    f"{type(exc).__name__}: {exc}"
                )

                if isinstance(record, dict):
                    result.append(dict(record))
                else:
                    result.append(record)

    migration_result = MigrationResult(
        migrated=migrated_count,
        skipped=skipped_count,
        failed=failed_count,
        errors=errors,
    )

    return result, migration_result


def read_scoped(
    records: list[dict],
    *,
    project_id: str,
    include_unassigned: bool = True,
) -> list[dict]:
    """
    Read records during the migration window.

    Migration-window decision:
      - A missing/invalid project_id means the record is UNASSIGNED.
      - By default, unassigned records remain visible during migration so
        users do not silently lose data while the backfill is incomplete.
      - include_unassigned=False provides strict project scoping and
        excludes those records.
      - A migrated record is returned only when its project_id matches
        project_id.

    Records are returned as copies and the input list is never mutated.
    """
    if not isinstance(records, list):
        raise TypeError("records must be a list")

    _validate_project_id(project_id, field_name="project_id")

    if not isinstance(include_unassigned, bool):
        raise TypeError("include_unassigned must be a boolean")

    scoped: list[dict] = []

    for index, record in enumerate(records):
        if not isinstance(record, dict):
            # read_scoped is a read operation. A malformed entry should
            # not make valid records disappear from the result.
            continue

        actual_project_id = record.get("project_id")

        if (
            isinstance(actual_project_id, str)
            and actual_project_id.strip()
        ):
            if actual_project_id == project_id:
                scoped.append(dict(record))

            continue

        # Missing/empty/invalid project_id means UNASSIGNED.
        if include_unassigned:
            scoped.append(dict(record))

    return scoped