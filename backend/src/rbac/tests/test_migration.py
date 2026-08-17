from __future__ import annotations

import copy

import pytest

from rbac.migration import (
    SCHEMA_VERSION,
    UNASSIGNED,
    MigrationResult,
    migrate_batch,
    migrate_record,
    needs_migration,
    read_scoped,
)


def make_record(
    sample_id: str = "s-1",
    org_id: str = "org-1",
    **extra,
) -> dict:
    record = {
        "sample_id": sample_id,
        "org_id": org_id,
        "name": "sample",
        "created_at": "2026-08-17T10:00:00Z",
    }
    record.update(extra)
    return record


def test_needs_migration_for_old_record():
    record = make_record()

    assert needs_migration(record) is True


def test_needs_migration_for_missing_project_id():
    record = make_record(
        schema_version=SCHEMA_VERSION,
    )

    assert needs_migration(record) is True


def test_needs_migration_for_missing_schema_version():
    record = make_record(
        project_id="project-1",
    )

    assert needs_migration(record) is True


def test_needs_migration_for_wrong_schema_version():
    record = make_record(
        project_id="project-1",
        schema_version=1,
    )

    assert needs_migration(record) is True


def test_already_migrated_record_does_not_need_migration():
    record = make_record(
        project_id="project-1",
        schema_version=SCHEMA_VERSION,
    )

    assert needs_migration(record) is False


def test_migrate_record_adds_project_and_schema_version():
    record = make_record()

    migrated = migrate_record(
        record,
        default_project_id=UNASSIGNED,
    )

    assert migrated == {
        **record,
        "project_id": UNASSIGNED,
        "schema_version": SCHEMA_VERSION,
    }


def test_migrate_record_preserves_existing_project_id():
    record = make_record(
        project_id="project-real",
        schema_version=1,
    )

    migrated = migrate_record(
        record,
        default_project_id=UNASSIGNED,
    )

    assert migrated["project_id"] == "project-real"
    assert migrated["schema_version"] == SCHEMA_VERSION


def test_migrate_record_already_migrated_is_exact_noop_in_value():
    record = make_record(
        project_id="project-real",
        schema_version=SCHEMA_VERSION,
    )

    original = copy.deepcopy(record)

    migrated = migrate_record(
        record,
        default_project_id=UNASSIGNED,
    )

    assert migrated == original
    assert migrated["project_id"] == "project-real"
    assert migrated["schema_version"] == SCHEMA_VERSION


def test_migrate_record_does_not_mutate_original():
    record = make_record()

    original = copy.deepcopy(record)

    migrated = migrate_record(
        record,
        default_project_id="project-1",
    )

    assert record == original
    assert migrated is not record


def test_migrate_record_preserves_extra_fields():
    record = make_record(
        project_id="project-1",
        metadata={
            "instrument": "fcs",
            "nested": {"value": 42},
        },
    )

    migrated = migrate_record(
        record,
        default_project_id=UNASSIGNED,
    )

    assert migrated["metadata"] == record["metadata"]
    assert migrated["project_id"] == "project-1"
    assert migrated["schema_version"] == SCHEMA_VERSION


def test_migrate_record_rejects_missing_sample_id():
    record = make_record()
    del record["sample_id"]

    with pytest.raises(ValueError, match="missing sample_id"):
        migrate_record(
            record,
            default_project_id=UNASSIGNED,
        )


def test_migrate_record_rejects_none():
    with pytest.raises(TypeError, match="record must be a dict"):
        migrate_record(
            None,
            default_project_id=UNASSIGNED,
        )


def test_migrate_record_rejects_wrong_sample_id_type():
    record = make_record(
        sample_id=123,
    )

    with pytest.raises(TypeError, match="sample_id must be a string"):
        migrate_record(
            record,
            default_project_id=UNASSIGNED,
        )


def test_migrate_record_rejects_empty_sample_id():
    record = make_record(
        sample_id="   ",
    )

    with pytest.raises(ValueError, match="sample_id must not be empty"):
        migrate_record(
            record,
            default_project_id=UNASSIGNED,
        )


def test_migrate_record_rejects_missing_org_id():
    record = make_record()
    del record["org_id"]

    with pytest.raises(ValueError, match="missing org_id"):
        migrate_record(
            record,
            default_project_id=UNASSIGNED,
        )


def test_migrate_record_rejects_future_schema_version():
    record = make_record(
        project_id="project-1",
        schema_version=SCHEMA_VERSION + 1,
    )

    with pytest.raises(
        ValueError,
        match="newer than the supported schema",
    ):
        migrate_record(
            record,
            default_project_id=UNASSIGNED,
        )


def test_migrate_batch_migrates_old_records():
    records = [
        make_record("s-1"),
        make_record("s-2"),
        make_record("s-3"),
    ]

    migrated, result = migrate_batch(
        records,
        default_project_id=UNASSIGNED,
    )

    assert all(
        record["project_id"] == UNASSIGNED
        for record in migrated
    )

    assert all(
        record["schema_version"] == SCHEMA_VERSION
        for record in migrated
    )

    assert result == MigrationResult(
        migrated=3,
        skipped=0,
        failed=0,
        errors=[],
    )


def test_migrate_batch_skips_already_migrated_records():
    records = [
        make_record(
            "s-1",
            project_id="project-1",
            schema_version=SCHEMA_VERSION,
        ),
        make_record("s-2"),
    ]

    migrated, result = migrate_batch(
        records,
        default_project_id=UNASSIGNED,
    )

    assert migrated[0]["project_id"] == "project-1"
    assert migrated[1]["project_id"] == UNASSIGNED

    assert result.migrated == 1
    assert result.skipped == 1
    assert result.failed == 0


def test_migrate_batch_does_not_mutate_input_list_or_records():
    records = [
        make_record("s-1"),
        make_record(
            "s-2",
            project_id="project-2",
            schema_version=SCHEMA_VERSION,
        ),
    ]

    original = copy.deepcopy(records)

    result_records, _ = migrate_batch(
        records,
        default_project_id=UNASSIGNED,
    )

    assert records == original
    assert result_records is not records

    for result_record, original_record in zip(
        result_records,
        records,
    ):
        assert result_record is not original_record


def test_migrate_batch_continues_after_malformed_record():
    records = [
        make_record("s-1"),
        None,
        make_record("s-3"),
    ]

    migrated, result = migrate_batch(
        records,
        default_project_id=UNASSIGNED,
    )

    assert result.migrated == 2
    assert result.skipped == 0
    assert result.failed == 1

    assert len(result.errors) == 1
    assert "record[1]" in result.errors[0]

    assert migrated[0]["schema_version"] == SCHEMA_VERSION
    assert migrated[2]["schema_version"] == SCHEMA_VERSION


def test_migrate_batch_continues_after_multiple_malformed_records():
    records = [
        make_record("s-1"),
        None,
        make_record("s-3"),
        {"org_id": "org-1"},
        make_record("s-5"),
    ]

    migrated, result = migrate_batch(
        records,
        default_project_id=UNASSIGNED,
    )

    assert result.migrated == 3
    assert result.failed == 2
    assert len(result.errors) == 2

    assert "record[1]" in result.errors[0]
    assert "record[3]" in result.errors[1]

    assert migrated[0]["schema_version"] == SCHEMA_VERSION
    assert migrated[2]["schema_version"] == SCHEMA_VERSION
    assert migrated[4]["schema_version"] == SCHEMA_VERSION


def test_migrate_batch_all_malformed_records():
    records = [
        None,
        {"org_id": "org-1"},
        {"sample_id": "s-3"},
    ]

    migrated, result = migrate_batch(
        records,
        default_project_id=UNASSIGNED,
    )

    assert len(migrated) == 3
    assert result.migrated == 0
    assert result.skipped == 0
    assert result.failed == 3
    assert len(result.errors) == 3


def test_migrate_batch_empty_list():
    migrated, result = migrate_batch(
        [],
        default_project_id=UNASSIGNED,
    )

    assert migrated == []
    assert result == MigrationResult(
        migrated=0,
        skipped=0,
        failed=0,
        errors=[],
    )


def test_migrate_batch_all_migrated():
    records = [
        make_record(
            "s-1",
            project_id="project-1",
            schema_version=SCHEMA_VERSION,
        ),
        make_record(
            "s-2",
            project_id="project-2",
            schema_version=SCHEMA_VERSION,
        ),
    ]

    migrated, result = migrate_batch(
        records,
        default_project_id=UNASSIGNED,
    )

    assert migrated == records
    assert result.migrated == 0
    assert result.skipped == 2
    assert result.failed == 0


def test_migrate_batch_respects_batch_size():
    records = [
        make_record(f"s-{index}")
        for index in range(10)
    ]

    migrated, result = migrate_batch(
        records,
        default_project_id=UNASSIGNED,
        batch_size=2,
    )

    assert len(migrated) == 10
    assert result.migrated == 10
    assert result.failed == 0


def test_migrate_batch_rejects_invalid_batch_size():
    with pytest.raises(ValueError, match="positive integer"):
        migrate_batch(
            [],
            default_project_id=UNASSIGNED,
            batch_size=0,
        )


def test_migrate_batch_rejects_boolean_batch_size():
    with pytest.raises(ValueError, match="positive integer"):
        migrate_batch(
            [],
            default_project_id=UNASSIGNED,
            batch_size=True,
        )


def test_migrate_batch_is_idempotent():
    records = [
        make_record("s-1"),
        make_record("s-2"),
        make_record(
            "s-3",
            project_id="project-existing",
            schema_version=SCHEMA_VERSION,
        ),
    ]

    first_result, first_stats = migrate_batch(
        records,
        default_project_id=UNASSIGNED,
    )

    second_result, second_stats = migrate_batch(
        first_result,
        default_project_id=UNASSIGNED,
    )

    assert second_result == first_result

    assert first_stats.migrated == 2
    assert first_stats.skipped == 1
    assert first_stats.failed == 0

    assert second_stats.migrated == 0
    assert second_stats.skipped == 3
    assert second_stats.failed == 0


def test_migrate_batch_second_run_never_reassigns_existing_projects():
    records = [
        make_record(
            "s-1",
            project_id="project-a",
            schema_version=SCHEMA_VERSION,
        ),
        make_record(
            "s-2",
            project_id="project-b",
            schema_version=SCHEMA_VERSION,
        ),
        make_record("s-3"),
    ]

    first_result, _ = migrate_batch(
        records,
        default_project_id=UNASSIGNED,
    )

    second_result, _ = migrate_batch(
        first_result,
        default_project_id="different-default-project",
    )

    assert second_result[0]["project_id"] == "project-a"
    assert second_result[1]["project_id"] == "project-b"
    assert second_result[2]["project_id"] == UNASSIGNED


def test_read_scoped_returns_matching_project_records():
    records = [
        make_record(
            "s-1",
            project_id="project-a",
            schema_version=SCHEMA_VERSION,
        ),
        make_record(
            "s-2",
            project_id="project-b",
            schema_version=SCHEMA_VERSION,
        ),
        make_record(
            "s-3",
            project_id="project-a",
            schema_version=SCHEMA_VERSION,
        ),
    ]

    result = read_scoped(
        records,
        project_id="project-a",
    )

    assert [record["sample_id"] for record in result] == [
        "s-1",
        "s-3",
    ]


def test_read_scoped_excludes_other_projects():
    records = [
        make_record(
            "s-1",
            project_id="project-a",
            schema_version=SCHEMA_VERSION,
        ),
        make_record(
            "s-2",
            project_id="project-b",
            schema_version=SCHEMA_VERSION,
        ),
    ]

    result = read_scoped(
        records,
        project_id="project-a",
        include_unassigned=False,
    )

    assert [record["sample_id"] for record in result] == ["s-1"]


def test_read_scoped_includes_unmigrated_records_by_default():
    records = [
        make_record(
            "s-1",
            project_id="project-a",
            schema_version=SCHEMA_VERSION,
        ),
        make_record("s-2"),
    ]

    result = read_scoped(
        records,
        project_id="project-a",
    )

    assert [record["sample_id"] for record in result] == [
        "s-1",
        "s-2",
    ]


def test_read_scoped_excludes_unmigrated_records_when_requested():
    records = [
        make_record(
            "s-1",
            project_id="project-a",
            schema_version=SCHEMA_VERSION,
        ),
        make_record("s-2"),
    ]

    result = read_scoped(
        records,
        project_id="project-a",
        include_unassigned=False,
    )

    assert [record["sample_id"] for record in result] == ["s-1"]


def test_read_scoped_can_explicitly_read_unassigned_records():
    records = [
        make_record("s-1"),
        make_record(
            "s-2",
            project_id="project-a",
            schema_version=SCHEMA_VERSION,
        ),
    ]

    result = read_scoped(
        records,
        project_id=UNASSIGNED,
        include_unassigned=True,
    )

    assert [record["sample_id"] for record in result] == ["s-1"]


def test_read_scoped_handles_empty_list():
    assert (
        read_scoped(
            [],
            project_id="project-a",
        )
        == []
    )


def test_read_scoped_does_not_mutate_input():
    records = [
        make_record("s-1"),
        make_record(
            "s-2",
            project_id="project-a",
            schema_version=SCHEMA_VERSION,
        ),
    ]

    original = copy.deepcopy(records)

    result = read_scoped(
        records,
        project_id="project-a",
    )

    assert records == original
    assert all(
        returned is not original_record
        for returned, original_record in zip(result, records)
        if returned["sample_id"] == original_record["sample_id"]
    )


def test_read_scoped_ignores_malformed_non_dict_entries():
    records = [
        make_record(
            "s-1",
            project_id="project-a",
            schema_version=SCHEMA_VERSION,
        ),
        None,
        "invalid",
        123,
    ]

    result = read_scoped(
        records,
        project_id="project-a",
        include_unassigned=False,
    )

    assert [record["sample_id"] for record in result] == ["s-1"]


def test_partial_migration_50_records_fail_at_25_then_rerun():
    records = [
        make_record(f"s-{index}")
        for index in range(1, 51)
    ]

    # Simulate a migration process that successfully commits the first
    # 24 records and then fails on record 25.
    first_24 = records[:24]

    migrated_first_part, first_stats = migrate_batch(
        first_24,
        default_project_id="project-1",
        batch_size=10,
    )

    assert first_stats.migrated == 24
    assert first_stats.failed == 0

    # The remaining records are still in their old shape.
    remaining = records[24:]

    assert all(
        "project_id" not in record
        for record in remaining
    )

    # Resume the migration with the already-migrated records plus
    # the remaining records.
    combined = migrated_first_part + remaining

    second_result, second_stats = migrate_batch(
        combined,
        default_project_id="project-1",
        batch_size=10,
    )

    assert len(second_result) == 50

    assert second_stats.migrated == 26
    assert second_stats.skipped == 24
    assert second_stats.failed == 0

    assert all(
        record["project_id"] == "project-1"
        for record in second_result
    )

    assert all(
        record["schema_version"] == SCHEMA_VERSION
        for record in second_result
    )

    assert [
        record["sample_id"]
        for record in second_result
    ] == [
        f"s-{index}"
        for index in range(1, 51)
    ]


def test_partial_migration_with_actual_failure_then_retry():
    """
    Simulate a real malformed record at position 25.

    First run:
      - records 1-24 migrate
      - record 25 fails
      - records 26-50 continue

    Then repair record 25 and rerun.

    The rerun must skip the already-migrated records and migrate
    only the repaired record.
    """
    records = [
        make_record(f"s-{index}")
        for index in range(1, 51)
    ]

    records[24] = {
        "org_id": "org-1",
        "name": "broken",
    }

    first_result, first_stats = migrate_batch(
        records,
        default_project_id="project-1",
        batch_size=10,
    )

    assert first_stats.migrated == 49
    assert first_stats.skipped == 0
    assert first_stats.failed == 1
    assert len(first_stats.errors) == 1
    assert "record[24]" in first_stats.errors[0]

    assert all(
        record["schema_version"] == SCHEMA_VERSION
        for index, record in enumerate(first_result)
        if index != 24
    )

    # Repair the failed record.
    first_result[24] = make_record("s-25")

    second_result, second_stats = migrate_batch(
        first_result,
        default_project_id="project-1",
        batch_size=10,
    )

    assert second_stats.migrated == 1
    assert second_stats.skipped == 49
    assert second_stats.failed == 0

    assert all(
        record["project_id"] == "project-1"
        for record in second_result
    )

    assert all(
        record["schema_version"] == SCHEMA_VERSION
        for record in second_result
    )

    assert len(second_result) == 50


def test_all_migrated_list_is_safe_to_run_repeatedly():
    records = [
        make_record(
            f"s-{index}",
            project_id=f"project-{index}",
            schema_version=SCHEMA_VERSION,
        )
        for index in range(1, 11)
    ]

    first, first_stats = migrate_batch(
        records,
        default_project_id=UNASSIGNED,
    )

    second, second_stats = migrate_batch(
        first,
        default_project_id=UNASSIGNED,
    )

    third, third_stats = migrate_batch(
        second,
        default_project_id="another-project",
    )

    assert first == second == third

    assert first_stats.migrated == 0
    assert first_stats.skipped == 10

    assert second_stats.migrated == 0
    assert second_stats.skipped == 10

    assert third_stats.migrated == 0
    assert third_stats.skipped == 10