from __future__ import annotations

import copy

import pytest

from rbac.sample_migration import (
    SCHEMA_VERSION,
    UNASSIGNED,
    MigrationResult,
    migrate_row,
    migrate_rows,
    needs_migration,
    scoped_sample_filter,
)


def make_row(
    sample_id: str = "s-1",
    *,
    row_id: int | None = 1,
    user_id: int | None = 10,
    **extra,
) -> dict:
    row = {
        "id": row_id,
        "user_id": user_id,
        "sample_id": sample_id,
        "processing_status": "pending",
        "upload_timestamp": "2026-08-19T10:00:00Z",
        "name": "sample",
    }

    row.update(extra)
    return row


# ---------------------------------------------------------------------------
# needs_migration
# ---------------------------------------------------------------------------


def test_needs_migration_for_old_row():
    row = make_row()

    assert needs_migration(row) is True


def test_needs_migration_when_project_id_missing():
    row = make_row(
        schema_version=SCHEMA_VERSION,
    )

    assert needs_migration(row) is True


def test_needs_migration_when_schema_version_missing():
    row = make_row(
        project_id="project-1",
    )

    assert needs_migration(row) is True


def test_needs_migration_when_schema_version_is_old():
    row = make_row(
        project_id="project-1",
        schema_version=1,
    )

    assert needs_migration(row) is True


def test_already_migrated_row_does_not_need_migration():
    row = make_row(
        project_id="project-1",
        schema_version=SCHEMA_VERSION,
    )

    assert needs_migration(row) is False


def test_empty_project_id_requires_migration():
    row = make_row(
        project_id="   ",
        schema_version=SCHEMA_VERSION,
    )

    assert needs_migration(row) is True


def test_none_project_id_requires_migration():
    row = make_row(
        project_id=None,
        schema_version=SCHEMA_VERSION,
    )

    assert needs_migration(row) is True


def test_boolean_schema_version_is_not_current():
    row = make_row(
        project_id="project-1",
        schema_version=True,
    )

    assert needs_migration(row) is True


# ---------------------------------------------------------------------------
# user_id behavior
# ---------------------------------------------------------------------------


def test_user_id_none_is_valid_and_migratable():
    row = make_row(
        user_id=None,
    )

    migrated = migrate_row(
        row,
        default_project_id=UNASSIGNED,
    )

    assert migrated["user_id"] is None
    assert migrated["project_id"] == UNASSIGNED
    assert migrated["schema_version"] == SCHEMA_VERSION


def test_user_id_is_preserved():
    row = make_row(user_id=123)

    migrated = migrate_row(
        row,
        default_project_id="project-1",
    )

    assert migrated["user_id"] == 123


def test_user_id_boolean_is_rejected():
    row = make_row(user_id=True)

    with pytest.raises(
        TypeError,
        match="user_id must be an integer or None",
    ):
        migrate_row(
            row,
            default_project_id=UNASSIGNED,
        )


def test_user_id_zero_is_rejected():
    row = make_row(user_id=0)

    with pytest.raises(
        ValueError,
        match="user_id must be a positive integer or None",
    ):
        migrate_row(
            row,
            default_project_id=UNASSIGNED,
        )


# ---------------------------------------------------------------------------
# migrate_row
# ---------------------------------------------------------------------------


def test_migrate_row_adds_project_and_schema_version():
    row = make_row()

    migrated = migrate_row(
        row,
        default_project_id=UNASSIGNED,
    )

    assert migrated == {
        **row,
        "project_id": UNASSIGNED,
        "schema_version": SCHEMA_VERSION,
    }


def test_migrate_row_preserves_existing_project_id():
    row = make_row(
        project_id="project-real",
        schema_version=1,
    )

    migrated = migrate_row(
        row,
        default_project_id=UNASSIGNED,
    )

    assert migrated["project_id"] == "project-real"
    assert migrated["schema_version"] == SCHEMA_VERSION


def test_migrate_row_does_not_replace_existing_project_with_default():
    row = make_row(
        project_id="project-a",
        schema_version=1,
    )

    migrated = migrate_row(
        row,
        default_project_id="project-b",
    )

    assert migrated["project_id"] == "project-a"


def test_migrate_row_already_migrated_is_value_noop():
    row = make_row(
        project_id="project-real",
        schema_version=SCHEMA_VERSION,
    )

    original = copy.deepcopy(row)

    migrated = migrate_row(
        row,
        default_project_id=UNASSIGNED,
    )

    assert migrated == original
    assert migrated["project_id"] == "project-real"
    assert migrated["schema_version"] == SCHEMA_VERSION


def test_migrate_row_does_not_mutate_original():
    row = make_row()

    original = copy.deepcopy(row)

    migrated = migrate_row(
        row,
        default_project_id="project-1",
    )

    assert row == original
    assert migrated is not row


def test_migrate_row_preserves_extra_fields():
    row = make_row(
        metadata={
            "instrument": "fcs",
            "nested": {"value": 42},
        },
    )

    migrated = migrate_row(
        row,
        default_project_id="project-1",
    )

    assert migrated["metadata"] == row["metadata"]
    assert migrated["project_id"] == "project-1"
    assert migrated["schema_version"] == SCHEMA_VERSION


def test_migrate_row_rejects_missing_sample_id():
    row = make_row()
    del row["sample_id"]

    with pytest.raises(
        ValueError,
        match="missing sample_id",
    ):
        migrate_row(
            row,
            default_project_id=UNASSIGNED,
        )


def test_migrate_row_rejects_none():
    with pytest.raises(
        TypeError,
        match="row must be a dict",
    ):
        migrate_row(
            None,
            default_project_id=UNASSIGNED,
        )


def test_migrate_row_rejects_wrong_sample_id_type():
    row = make_row(sample_id=123)

    with pytest.raises(
        TypeError,
        match="sample_id must be a string",
    ):
        migrate_row(
            row,
            default_project_id=UNASSIGNED,
        )


def test_migrate_row_rejects_empty_sample_id():
    row = make_row(sample_id="   ")

    with pytest.raises(
        ValueError,
        match="sample_id must not be empty",
    ):
        migrate_row(
            row,
            default_project_id=UNASSIGNED,
        )


def test_migrate_row_rejects_invalid_id_type():
    row = make_row(row_id="1")

    with pytest.raises(
        TypeError,
        match="id must be an integer",
    ):
        migrate_row(
            row,
            default_project_id=UNASSIGNED,
        )


def test_migrate_row_rejects_boolean_id():
    row = make_row(row_id=True)

    with pytest.raises(
        TypeError,
        match="id must be an integer",
    ):
        migrate_row(
            row,
            default_project_id=UNASSIGNED,
        )


def test_migrate_row_rejects_non_positive_id():
    row = make_row(row_id=0)

    with pytest.raises(
        ValueError,
        match="id must be a positive integer",
    ):
        migrate_row(
            row,
            default_project_id=UNASSIGNED,
        )


def test_migrate_row_rejects_future_schema_version():
    row = make_row(
        project_id="project-1",
        schema_version=SCHEMA_VERSION + 1,
    )

    with pytest.raises(
        ValueError,
        match="newer than the supported schema",
    ):
        migrate_row(
            row,
            default_project_id=UNASSIGNED,
        )


def test_migrate_row_rejects_future_schema_even_if_project_exists():
    row = make_row(
        project_id="project-1",
        schema_version=999,
    )

    with pytest.raises(
        ValueError,
        match="newer than the supported schema",
    ):
        migrate_row(
            row,
            default_project_id=UNASSIGNED,
        )


# ---------------------------------------------------------------------------
# migrate_rows validation
# ---------------------------------------------------------------------------


def test_migrate_rows_rejects_non_list():
    with pytest.raises(
        TypeError,
        match="rows must be a list",
    ):
        migrate_rows(
            (),
            default_project_id=UNASSIGNED,
        )


def test_migrate_rows_rejects_empty_default_project():
    with pytest.raises(
        ValueError,
        match="default_project_id must not be empty",
    ):
        migrate_rows(
            [],
            default_project_id="   ",
        )


def test_migrate_rows_rejects_non_string_default_project():
    with pytest.raises(
        TypeError,
        match="default_project_id must be a string",
    ):
        migrate_rows(
            [],
            default_project_id=None,
        )


def test_migrate_rows_rejects_invalid_batch_size():
    with pytest.raises(
        ValueError,
        match="positive integer",
    ):
        migrate_rows(
            [],
            default_project_id=UNASSIGNED,
            batch_size=0,
        )


def test_migrate_rows_rejects_boolean_batch_size():
    with pytest.raises(
        ValueError,
        match="positive integer",
    ):
        migrate_rows(
            [],
            default_project_id=UNASSIGNED,
            batch_size=True,
        )


# ---------------------------------------------------------------------------
# migrate_rows basic behavior
# ---------------------------------------------------------------------------


def test_migrate_rows_migrates_old_rows():
    rows = [
        make_row("s-1"),
        make_row("s-2"),
        make_row("s-3"),
    ]

    migrated, result = migrate_rows(
        rows,
        default_project_id=UNASSIGNED,
    )

    assert all(
        row["project_id"] == UNASSIGNED
        for row in migrated
    )

    assert all(
        row["schema_version"] == SCHEMA_VERSION
        for row in migrated
    )

    assert result == MigrationResult(
        migrated=3,
        skipped=0,
        failed=0,
        errors=[],
    )


def test_migrate_rows_skips_current_rows():
    rows = [
        make_row(
            "s-1",
            project_id="project-1",
            schema_version=SCHEMA_VERSION,
        ),
        make_row("s-2"),
    ]

    migrated, result = migrate_rows(
        rows,
        default_project_id=UNASSIGNED,
    )

    assert migrated[0]["project_id"] == "project-1"
    assert migrated[1]["project_id"] == UNASSIGNED

    assert result.migrated == 1
    assert result.skipped == 1
    assert result.failed == 0


def test_migrate_rows_does_not_mutate_input():
    rows = [
        make_row("s-1"),
        make_row(
            "s-2",
            project_id="project-2",
            schema_version=SCHEMA_VERSION,
        ),
    ]

    original = copy.deepcopy(rows)

    result_rows, _ = migrate_rows(
        rows,
        default_project_id=UNASSIGNED,
    )

    assert rows == original
    assert result_rows is not rows

    for returned, original_row in zip(
        result_rows,
        rows,
    ):
        assert returned is not original_row


def test_migrate_rows_continues_after_malformed_row():
    rows = [
        make_row("s-1"),
        None,
        make_row("s-3"),
    ]

    migrated, result = migrate_rows(
        rows,
        default_project_id=UNASSIGNED,
    )

    assert result.migrated == 2
    assert result.skipped == 0
    assert result.failed == 1

    assert len(result.errors) == 1
    assert "row[1]" in result.errors[0]

    assert migrated[0]["schema_version"] == SCHEMA_VERSION
    assert migrated[2]["schema_version"] == SCHEMA_VERSION


def test_migrate_rows_continues_after_multiple_malformed_rows():
    rows = [
        make_row("s-1"),
        None,
        make_row("s-3"),
        {"id": 4},
        make_row("s-5"),
    ]

    migrated, result = migrate_rows(
        rows,
        default_project_id=UNASSIGNED,
    )

    assert result.migrated == 3
    assert result.failed == 2
    assert len(result.errors) == 2

    assert "row[1]" in result.errors[0]
    assert "row[3]" in result.errors[1]

    assert migrated[0]["schema_version"] == SCHEMA_VERSION
    assert migrated[2]["schema_version"] == SCHEMA_VERSION
    assert migrated[4]["schema_version"] == SCHEMA_VERSION


def test_migrate_rows_all_malformed():
    rows = [
        None,
        {"id": 1},
        {"sample_id": ""},
    ]

    migrated, result = migrate_rows(
        rows,
        default_project_id=UNASSIGNED,
    )

    assert len(migrated) == 3
    assert result.migrated == 0
    assert result.skipped == 0
    assert result.failed == 3
    assert len(result.errors) == 3


def test_migrate_rows_empty_list():
    migrated, result = migrate_rows(
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


def test_migrate_rows_all_current():
    rows = [
        make_row(
            "s-1",
            project_id="project-1",
            schema_version=SCHEMA_VERSION,
        ),
        make_row(
            "s-2",
            project_id="project-2",
            schema_version=SCHEMA_VERSION,
        ),
    ]

    migrated, result = migrate_rows(
        rows,
        default_project_id=UNASSIGNED,
    )

    assert migrated == rows
    assert result.migrated == 0
    assert result.skipped == 2
    assert result.failed == 0


def test_migrate_rows_respects_batch_size():
    rows = [
        make_row(f"s-{index}")
        for index in range(10)
    ]

    migrated, result = migrate_rows(
        rows,
        default_project_id=UNASSIGNED,
        batch_size=2,
    )

    assert len(migrated) == 10
    assert result.migrated == 10
    assert result.failed == 0


def test_batch_size_does_not_change_result():
    rows = [
        make_row(f"s-{index}")
        for index in range(20)
    ]

    result_one, stats_one = migrate_rows(
        rows,
        default_project_id="project-1",
        batch_size=1,
    )

    result_many, stats_many = migrate_rows(
        rows,
        default_project_id="project-1",
        batch_size=500,
    )

    assert result_one == result_many
    assert stats_one == stats_many


# ---------------------------------------------------------------------------
# Idempotency and resume safety
# ---------------------------------------------------------------------------


def test_migrate_rows_is_idempotent():
    rows = [
        make_row("s-1"),
        make_row("s-2"),
        make_row(
            "s-3",
            project_id="project-existing",
            schema_version=SCHEMA_VERSION,
        ),
    ]

    first_result, first_stats = migrate_rows(
        rows,
        default_project_id=UNASSIGNED,
    )

    second_result, second_stats = migrate_rows(
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


def test_second_run_never_reassigns_existing_projects():
    rows = [
        make_row(
            "s-1",
            project_id="project-a",
            schema_version=SCHEMA_VERSION,
        ),
        make_row(
            "s-2",
            project_id="project-b",
            schema_version=SCHEMA_VERSION,
        ),
        make_row("s-3"),
    ]

    first_result, _ = migrate_rows(
        rows,
        default_project_id=UNASSIGNED,
    )

    second_result, _ = migrate_rows(
        first_result,
        default_project_id="different-project",
    )

    assert second_result[0]["project_id"] == "project-a"
    assert second_result[1]["project_id"] == "project-b"
    assert second_result[2]["project_id"] == UNASSIGNED


def test_current_rows_are_safe_to_run_repeatedly():
    rows = [
        make_row(
            f"s-{index}",
            project_id=f"project-{index}",
            schema_version=SCHEMA_VERSION,
        )
        for index in range(1, 11)
    ]

    first, first_stats = migrate_rows(
        rows,
        default_project_id=UNASSIGNED,
    )

    second, second_stats = migrate_rows(
        first,
        default_project_id=UNASSIGNED,
    )

    third, third_stats = migrate_rows(
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


def test_partial_migration_can_resume():
    rows = [
        make_row(f"s-{index}")
        for index in range(1, 51)
    ]

    first_part = rows[:24]

    migrated_first_part, first_stats = migrate_rows(
        first_part,
        default_project_id="project-1",
        batch_size=10,
    )

    assert first_stats.migrated == 24
    assert first_stats.failed == 0

    remaining = rows[24:]

    assert all(
        "project_id" not in row
        for row in remaining
    )

    combined = migrated_first_part + remaining

    second_result, second_stats = migrate_rows(
        combined,
        default_project_id="project-1",
        batch_size=10,
    )

    assert len(second_result) == 50
    assert second_stats.migrated == 26
    assert second_stats.skipped == 24
    assert second_stats.failed == 0

    assert all(
        row["project_id"] == "project-1"
        for row in second_result
    )

    assert all(
        row["schema_version"] == SCHEMA_VERSION
        for row in second_result
    )


def test_failed_row_can_be_repaired_and_retried():
    rows = [
        make_row(f"s-{index}")
        for index in range(1, 51)
    ]

    rows[24] = {
        "id": 25,
        "user_id": None,
        "processing_status": "pending",
        "upload_timestamp": "2026-08-19T10:00:00Z",
    }

    first_result, first_stats = migrate_rows(
        rows,
        default_project_id="project-1",
        batch_size=10,
    )

    assert first_stats.migrated == 49
    assert first_stats.skipped == 0
    assert first_stats.failed == 1
    assert len(first_stats.errors) == 1
    assert "row[24]" in first_stats.errors[0]

    first_result[24] = make_row("s-25")

    second_result, second_stats = migrate_rows(
        first_result,
        default_project_id="project-1",
        batch_size=10,
    )

    assert second_stats.migrated == 1
    assert second_stats.skipped == 49
    assert second_stats.failed == 0

    assert len(second_result) == 50


# ---------------------------------------------------------------------------
# Live-row / concurrent insertion semantics
# ---------------------------------------------------------------------------


def test_rows_inserted_after_snapshot_require_second_pass():
    initial_rows = [
        make_row("s-1"),
        make_row("s-2"),
    ]

    migrated_snapshot, first_stats = migrate_rows(
        initial_rows,
        default_project_id="project-1",
    )

    assert first_stats.migrated == 2

    # Simulate rows inserted after the first read/backfill snapshot.
    live_inserted_rows = [
        make_row("s-3"),
        make_row(
            "s-4",
            project_id="project-4",
            schema_version=SCHEMA_VERSION,
        ),
    ]

    # The first migration cannot claim rows that were not in its input.
    assert all(
        row["sample_id"] not in {"s-3", "s-4"}
        for row in migrated_snapshot
    )

    # A second pass over the newly observed rows handles them.
    second_result, second_stats = migrate_rows(
        live_inserted_rows,
        default_project_id="project-1",
    )

    assert second_stats.migrated == 1
    assert second_stats.skipped == 1

    assert second_result[0]["project_id"] == "project-1"
    assert second_result[1]["project_id"] == "project-4"


def test_already_correct_row_inserted_mid_run_is_not_changed():
    row = make_row(
        "s-live",
        project_id="project-live",
        schema_version=SCHEMA_VERSION,
    )

    result, stats = migrate_rows(
        [row],
        default_project_id="project-default",
    )

    assert result == [row]
    assert stats.migrated == 0
    assert stats.skipped == 1
    assert stats.failed == 0


# ---------------------------------------------------------------------------
# scoped_sample_filter
# ---------------------------------------------------------------------------


def test_scoped_sample_filter_returns_matching_project_rows():
    rows = [
        make_row(
            "s-1",
            project_id="project-a",
            schema_version=SCHEMA_VERSION,
        ),
        make_row(
            "s-2",
            project_id="project-b",
            schema_version=SCHEMA_VERSION,
        ),
        make_row(
            "s-3",
            project_id="project-a",
            schema_version=SCHEMA_VERSION,
        ),
    ]

    result = scoped_sample_filter(
        rows,
        project_id="project-a",
    )

    assert [
        row["sample_id"]
        for row in result
    ] == ["s-1", "s-3"]


def test_scoped_sample_filter_excludes_other_projects():
    rows = [
        make_row(
            "s-1",
            project_id="project-a",
            schema_version=SCHEMA_VERSION,
        ),
        make_row(
            "s-2",
            project_id="project-b",
            schema_version=SCHEMA_VERSION,
        ),
    ]

    result = scoped_sample_filter(
        rows,
        project_id="project-a",
        include_unassigned=False,
    )

    assert [
        row["sample_id"]
        for row in result
    ] == ["s-1"]


def test_scoped_sample_filter_includes_unassigned_by_default():
    rows = [
        make_row(
            "s-1",
            project_id="project-a",
            schema_version=SCHEMA_VERSION,
        ),
        make_row("s-2"),
    ]

    result = scoped_sample_filter(
        rows,
        project_id="project-a",
    )

    assert [
        row["sample_id"]
        for row in result
    ] == ["s-1", "s-2"]


def test_scoped_sample_filter_excludes_unassigned_when_requested():
    rows = [
        make_row(
            "s-1",
            project_id="project-a",
            schema_version=SCHEMA_VERSION,
        ),
        make_row("s-2"),
    ]

    result = scoped_sample_filter(
        rows,
        project_id="project-a",
        include_unassigned=False,
    )

    assert [
        row["sample_id"]
        for row in result
    ] == ["s-1"]


def test_scoped_sample_filter_can_read_unassigned_explicitly():
    rows = [
        make_row("s-1"),
        make_row(
            "s-2",
            project_id="project-a",
            schema_version=SCHEMA_VERSION,
        ),
    ]

    result = scoped_sample_filter(
        rows,
        project_id=UNASSIGNED,
        include_unassigned=True,
    )

    assert [
        row["sample_id"]
        for row in result
    ] == ["s-1"]


def test_scoped_sample_filter_treats_empty_project_as_unassigned():
    rows = [
        make_row(
            "s-1",
            project_id="",
            schema_version=SCHEMA_VERSION,
        ),
        make_row(
            "s-2",
            project_id="project-a",
            schema_version=SCHEMA_VERSION,
        ),
    ]

    result = scoped_sample_filter(
        rows,
        project_id="project-a",
    )

    assert [
        row["sample_id"]
        for row in result
    ] == ["s-1", "s-2"]


def test_scoped_sample_filter_treats_none_project_as_unassigned():
    rows = [
        make_row(
            "s-1",
            project_id=None,
            schema_version=SCHEMA_VERSION,
        ),
    ]

    result = scoped_sample_filter(
        rows,
        project_id="project-a",
    )

    assert [
        row["sample_id"]
        for row in result
    ] == ["s-1"]


def test_scoped_sample_filter_handles_malformed_entries():
    rows = [
        make_row(
            "s-1",
            project_id="project-a",
            schema_version=SCHEMA_VERSION,
        ),
        None,
        "invalid",
        123,
    ]

    result = scoped_sample_filter(
        rows,
        project_id="project-a",
        include_unassigned=False,
    )

    assert [
        row["sample_id"]
        for row in result
    ] == ["s-1"]


def test_scoped_sample_filter_handles_empty_list():
    assert (
        scoped_sample_filter(
            [],
            project_id="project-a",
        )
        == []
    )


def test_scoped_sample_filter_does_not_mutate_input():
    rows = [
        make_row("s-1"),
        make_row(
            "s-2",
            project_id="project-a",
            schema_version=SCHEMA_VERSION,
        ),
    ]

    original = copy.deepcopy(rows)

    result = scoped_sample_filter(
        rows,
        project_id="project-a",
    )

    assert rows == original

    for returned in result:
        matching_original = next(
            row
            for row in rows
            if row["sample_id"] == returned["sample_id"]
        )

        assert returned is not matching_original


def test_scoped_sample_filter_rejects_invalid_project_id():
    with pytest.raises(
        ValueError,
        match="project_id must not be empty",
    ):
        scoped_sample_filter(
            [],
            project_id="   ",
        )


def test_scoped_sample_filter_rejects_non_string_project_id():
    with pytest.raises(
        TypeError,
        match="project_id must be a string",
    ):
        scoped_sample_filter(
            [],
            project_id=None,
        )


def test_scoped_sample_filter_rejects_non_boolean_include_unassigned():
    with pytest.raises(
        TypeError,
        match="include_unassigned must be a boolean",
    ):
        scoped_sample_filter(
            [],
            project_id="project-a",
            include_unassigned=1,
        )