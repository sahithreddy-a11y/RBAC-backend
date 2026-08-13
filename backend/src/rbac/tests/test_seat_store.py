import pytest

from backend.src.rbac.seat_store import SeatStore, VersionedSeatState
from backend.src.rbac.seats import SeatState


def make_versioned_state(
    seats_total: int = 10,
    members: dict[str, str] | None = None,
    version: int = 0,
) -> VersionedSeatState:
    members = {} if members is None else dict(members)

    return VersionedSeatState(
        state=SeatState(
            seats_total=seats_total,
            seats_used=len(members),
            members=members,
        ),
        version=version,
    )


def test_read_returns_initial_state():
    initial = make_versioned_state(version=7)
    store = SeatStore(initial)

    assert store.read() == initial


def test_successful_commit_increments_version_by_one():
    store = SeatStore(make_versioned_state())

    result = store.commit(
        0,
        "invite",
        "alice@example.com",
        request_id="r1",
    )

    assert result.ok is True
    assert result.reason == "ok"
    assert result.state.version == 1
    assert result.state.state.seats_used == 1
    assert result.state.state.members == {
        "alice@example.com": "pending"
    }


def test_ab_interleaving_produces_version_conflict():
    store = SeatStore(make_versioned_state(version=7))

    state_a = store.read()
    state_b = store.read()

    assert state_a.version == 7
    assert state_b.version == 7

    result_a = store.commit(
        7,
        "invite",
        "alice@example.com",
        request_id="r1",
    )

    assert result_a.ok is True
    assert result_a.state.version == 8

    result_b = store.commit(
        7,
        "invite",
        "bob@example.com",
        request_id="r2",
    )

    assert result_b.ok is False
    assert result_b.reason == "version_conflict"
    assert result_b.state == store.read()

    final = store.read()

    assert final.version == 8
    assert final.state.seats_used == 1
    assert final.state.members == {
        "alice@example.com": "pending"
    }


def test_version_conflict_leaves_state_unchanged():
    store = SeatStore(make_versioned_state(version=7))

    store.commit(
        7,
        "invite",
        "alice@example.com",
        request_id="r1",
    )

    before_conflict = store.read()

    result = store.commit(
        7,
        "invite",
        "bob@example.com",
        request_id="r2",
    )

    assert result.ok is False
    assert result.reason == "version_conflict"
    assert result.state == before_conflict
    assert store.read() == before_conflict


def test_replaying_request_returns_duplicate_request():
    store = SeatStore(make_versioned_state())

    first = store.commit(
        0,
        "invite",
        "alice@example.com",
        request_id="r1",
    )

    second = store.commit(
        0,
        "invite",
        "alice@example.com",
        request_id="r1",
    )

    assert first.ok is True
    assert first.reason == "ok"

    assert second.ok is True
    assert second.reason == "duplicate_request"
    assert second.state == first.state
    assert store.read() == first.state


def test_replaying_request_at_different_version_is_duplicate():
    store = SeatStore(make_versioned_state())

    first = store.commit(
        0,
        "invite",
        "alice@example.com",
        request_id="r1",
    )

    duplicate = store.commit(
        999,
        "invite",
        "alice@example.com",
        request_id="r1",
    )

    assert duplicate.ok is True
    assert duplicate.reason == "duplicate_request"
    assert duplicate.state == first.state


def test_different_request_id_for_same_member_returns_already_member():
    store = SeatStore(make_versioned_state())

    first = store.commit(
        0,
        "invite",
        "alice@example.com",
        request_id="r1",
    )

    second = store.commit(
        1,
        "invite",
        "alice@example.com",
        request_id="r2",
    )

    assert first.ok is True
    assert second.ok is False
    assert second.reason == "already_member"
    assert second.state == store.read()
    assert second.state.state.seats_used == 1


def test_expected_version_mismatch_does_not_change_state():
    store = SeatStore(make_versioned_state(version=3))

    before = store.read()

    result = store.commit(
        4,
        "invite",
        "alice@example.com",
        request_id="r1",
    )

    assert result.ok is False
    assert result.reason == "version_conflict"
    assert result.state == before
    assert store.read() == before


def test_no_seats_available_does_not_increment_version():
    store = SeatStore(make_versioned_state(seats_total=0))

    result = store.commit(
        0,
        "invite",
        "alice@example.com",
        request_id="r1",
    )

    assert result.ok is False
    assert result.reason == "no_seats_available"
    assert result.state == store.read()
    assert store.read().version == 0


def test_unknown_operation_does_not_change_state():
    store = SeatStore(make_versioned_state())

    before = store.read()

    result = store.commit(
        0,
        "something_else",
        "alice@example.com",
        request_id="r1",
    )

    assert result.ok is False
    assert result.reason == "unknown_operation"
    assert result.state == before
    assert store.read() == before


def test_request_id_memory_is_bounded():
    store = SeatStore(make_versioned_state(seats_total=2000))

    for number in range(1001):
        result = store.commit(
            number,
            "invite",
            f"user{number}@example.com",
            request_id=f"r{number}",
        )

        assert result.ok is True

    assert len(store._completed_requests) == store.REQUEST_ID_LIMIT
    assert "r0" not in store._completed_requests
    assert "r1" in store._completed_requests


def test_conflicted_request_is_not_recorded():
    store = SeatStore(make_versioned_state())

    conflict = store.commit(
        1,
        "invite",
        "alice@example.com",
        request_id="r1",
    )

    assert conflict.reason == "version_conflict"

    successful = store.commit(
        0,
        "invite",
        "alice@example.com",
        request_id="r1",
    )

    assert successful.ok is True
    assert successful.reason == "ok"


def test_activate_increments_version():
    store = SeatStore(
        make_versioned_state(
            members={"alice@example.com": "pending"},
            version=10,
        )
    )

    result = store.commit(
        10,
        "activate",
        "alice@example.com",
        request_id="r1",
    )

    assert result.ok is True
    assert result.state.version == 11
    assert result.state.state.members["alice@example.com"] == "active"


def test_cancel_invite_increments_version():
    store = SeatStore(
        make_versioned_state(
            members={"bob@example.com": "pending"},
            version=20,
        )
    )

    result = store.commit(
        20,
        "cancel_invite",
        "bob@example.com",
        request_id="r1",
    )

    assert result.ok is True
    assert result.state.version == 21
    assert "bob@example.com" not in result.state.state.members


def test_deactivate_increments_version():
    store = SeatStore(
        make_versioned_state(
            members={"carol@example.com": "active"},
            version=30,
        )
    )

    result = store.commit(
        30,
        "deactivate",
        "carol@example.com",
        request_id="r1",
    )

    assert result.ok is True
    assert result.state.version == 31
    assert "carol@example.com" not in result.state.state.members


def test_initial_state_must_be_versioned_seat_state():
    with pytest.raises(TypeError):
        SeatStore(None)


def test_negative_version_is_rejected():
    with pytest.raises(ValueError):
        SeatStore(
            VersionedSeatState(
                state=SeatState(
                    seats_total=1,
                    seats_used=0,
                    members={},
                ),
                version=-1,
            )
        )


def test_boolean_expected_version_is_rejected():
    store = SeatStore(make_versioned_state())

    with pytest.raises(ValueError):
        store.commit(
            True,
            "invite",
            "alice@example.com",
            request_id="r1",
        )


def test_empty_request_id_is_rejected():
    store = SeatStore(make_versioned_state())

    with pytest.raises(ValueError):
        store.commit(
            0,
            "invite",
            "alice@example.com",
            request_id="",
        )