import pytest

from backend.src.rbac.seats import (
    SeatResult,
    SeatState,
    activate,
    cancel_invite,
    deactivate,
    invite,
)


def make_state(
    seats_total: int = 10,
    members: dict[str, str] | None = None,
) -> SeatState:
    members = {} if members is None else dict(members)

    return SeatState(
        seats_total=seats_total,
        seats_used=len(members),
        members=members,
    )


def assert_invariants(state: SeatState) -> None:
    assert 0 <= state.seats_used <= state.seats_total
    assert state.seats_used == len(state.members)

    for status in state.members.values():
        assert status in {"pending", "active"}


def test_ten_invites_consume_exactly_ten_seats():
    state = make_state(10)

    for number in range(10):
        result = invite(state, f"user{number}@example.com")

        assert result.ok is True
        assert result.reason == "ok"

        state = result.state
        assert_invariants(state)

    assert state.seats_used == 10
    assert len(state.members) == 10


def test_eleventh_invite_is_rejected_and_state_is_unchanged():
    state = make_state(10)

    for number in range(10):
        state = invite(
            state,
            f"user{number}@example.com",
        ).state

    before = state

    result = invite(state, "user10@example.com")

    assert result.ok is False
    assert result.reason == "no_seats_available"
    assert result.state.seats_used == 10
    assert result.state.members == before.members
    assert "user10@example.com" not in result.state.members

    assert_invariants(result.state)


def test_invite_reserves_one_seat_and_creates_pending_member():
    state = make_state(5)

    result = invite(state, "alice@example.com")

    assert result.ok is True
    assert result.reason == "ok"
    assert result.state.seats_used == 1
    assert result.state.members == {
        "alice@example.com": "pending",
    }

    assert_invariants(result.state)


def test_invite_then_activate_consumes_only_one_seat():
    state = make_state(5)

    invited = invite(state, "alice@example.com")

    assert invited.state.seats_used == 1
    assert invited.state.members["alice@example.com"] == "pending"

    activated = activate(
        invited.state,
        "alice@example.com",
    )

    assert activated.ok is True
    assert activated.reason == "ok"
    assert activated.state.seats_used == 1
    assert activated.state.members["alice@example.com"] == "active"

    assert_invariants(activated.state)


def test_invite_then_cancel_releases_the_seat():
    state = make_state(5)

    invited = invite(state, "alice@example.com")
    cancelled = cancel_invite(
        invited.state,
        "alice@example.com",
    )

    assert cancelled.ok is True
    assert cancelled.reason == "ok"
    assert cancelled.state.seats_used == 0
    assert cancelled.state.members == {}

    assert_invariants(cancelled.state)


def test_duplicate_invite_consumes_only_one_seat():
    state = make_state(5)

    first = invite(state, "alice@example.com")
    second = invite(
        first.state,
        "alice@example.com",
    )

    assert first.ok is True
    assert second.ok is False
    assert second.reason == "already_member"
    assert second.state.seats_used == 1
    assert second.state.members == {
        "alice@example.com": "pending",
    }

    assert_invariants(second.state)


def test_email_case_variants_are_treated_as_same_member():
    state = make_state(5)

    first = invite(
        state,
        "Bob@X.com",
    )

    second = invite(
        first.state,
        "bob@x.com",
    )

    assert first.ok is True
    assert first.state.seats_used == 1
    assert first.state.members == {
        "bob@x.com": "pending",
    }

    assert second.ok is False
    assert second.reason == "already_member"
    assert second.state.seats_used == 1
    assert second.state.members == {
        "bob@x.com": "pending",
    }

    assert_invariants(second.state)


def test_duplicate_invite_for_active_member_is_also_idempotent():
    state = make_state(5)

    invited = invite(state, "alice@example.com")
    activated = activate(
        invited.state,
        "alice@example.com",
    )

    duplicate = invite(
        activated.state,
        "alice@example.com",
    )

    assert duplicate.ok is False
    assert duplicate.reason == "already_member"
    assert duplicate.state.seats_used == 1
    assert duplicate.state.members["alice@example.com"] == "active"

    assert_invariants(duplicate.state)


def test_activate_twice_does_not_change_seat_count():
    state = make_state(5)

    invited = invite(state, "alice@example.com")
    first = activate(
        invited.state,
        "alice@example.com",
    )
    second = activate(
        first.state,
        "alice@example.com",
    )

    assert first.ok is True
    assert first.state.seats_used == 1

    assert second.ok is False
    assert second.reason == "already_active"
    assert second.state.seats_used == 1
    assert second.state.members["alice@example.com"] == "active"

    assert_invariants(second.state)


def test_cancel_unknown_member_does_not_change_state():
    state = make_state(
        5,
        {"alice@example.com": "pending"},
    )

    result = cancel_invite(
        state,
        "unknown@example.com",
    )

    assert result.ok is False
    assert result.reason == "not_a_member"
    assert result.state.seats_used == 1
    assert result.state.members == {
        "alice@example.com": "pending",
    }

    assert_invariants(result.state)


def test_cancel_active_member_does_not_remove_active_member():
    state = make_state(
        5,
        {"alice@example.com": "active"},
    )

    result = cancel_invite(
        state,
        "alice@example.com",
    )

    assert result.ok is False
    assert result.reason == "no_change"
    assert result.state.seats_used == 1
    assert result.state.members["alice@example.com"] == "active"

    assert_invariants(result.state)


def test_deactivate_releases_exactly_one_seat():
    state = make_state(
        5,
        {"alice@example.com": "active"},
    )

    result = deactivate(
        state,
        "alice@example.com",
    )

    assert result.ok is True
    assert result.reason == "ok"
    assert result.state.seats_used == 0
    assert result.state.members == {}

    assert_invariants(result.state)


def test_deactivate_twice_releases_only_one_seat():
    state = make_state(
        5,
        {"alice@example.com": "active"},
    )

    first = deactivate(
        state,
        "alice@example.com",
    )
    second = deactivate(
        first.state,
        "alice@example.com",
    )

    assert first.ok is True
    assert first.state.seats_used == 0

    assert second.ok is False
    assert second.reason == "not_a_member"
    assert second.state.seats_used == 0
    assert second.state.members == {}

    assert_invariants(second.state)


def test_deactivate_pending_member_does_not_release_seat():
    state = make_state(
        5,
        {"alice@example.com": "pending"},
    )

    result = deactivate(
        state,
        "alice@example.com",
    )

    assert result.ok is False
    assert result.reason == "no_change"
    assert result.state.seats_used == 1
    assert result.state.members["alice@example.com"] == "pending"

    assert_invariants(result.state)


def test_activate_unknown_member_does_not_change_state():
    state = make_state(
        5,
        {"alice@example.com": "pending"},
    )

    result = activate(
        state,
        "unknown@example.com",
    )

    assert result.ok is False
    assert result.reason == "not_a_member"
    assert result.state.seats_used == 1
    assert result.state.members == {
        "alice@example.com": "pending",
    }

    assert_invariants(result.state)


def test_input_state_is_not_mutated():
    state = make_state(5)

    original_members = dict(state.members)
    original_used = state.seats_used

    result = invite(
        state,
        "alice@example.com",
    )

    assert state.seats_used == original_used
    assert state.members == original_members
    assert state.members == {}

    assert result.state is not state
    assert result.state.members is not state.members


def test_input_state_is_not_mutated_when_activating():
    state = make_state(
        5,
        {"alice@example.com": "pending"},
    )

    original_members = dict(state.members)

    result = activate(
        state,
        "alice@example.com",
    )

    assert state.members == original_members
    assert state.members["alice@example.com"] == "pending"
    assert result.state.members["alice@example.com"] == "active"
    assert result.state.members is not state.members


def test_input_state_is_not_mutated_when_removing_member():
    state = make_state(
        5,
        {"alice@example.com": "active"},
    )

    result = deactivate(
        state,
        "alice@example.com",
    )

    assert state.members == {
        "alice@example.com": "active",
    }

    assert result.state.members == {}
    assert result.state.members is not state.members


def test_whitespace_around_email_is_normalized():
    state = make_state(5)

    result = invite(
        state,
        "  alice@example.com  ",
    )

    assert result.ok is True
    assert result.state.members == {
        "alice@example.com": "pending",
    }


@pytest.mark.parametrize(
    "operation",
    [
        lambda state: invite(state, ""),
        lambda state: activate(state, ""),
        lambda state: cancel_invite(state, ""),
        lambda state: deactivate(state, ""),
    ],
)
def test_empty_email_is_rejected(operation):
    state = make_state(5)

    with pytest.raises(ValueError):
        operation(state)


@pytest.mark.parametrize(
    "operation",
    [
        lambda state: invite(state, None),
        lambda state: activate(state, None),
        lambda state: cancel_invite(state, None),
        lambda state: deactivate(state, None),
    ],
)
def test_non_string_email_is_rejected(operation):
    state = make_state(5)

    with pytest.raises(ValueError):
        operation(state)


def test_zero_seat_organization_cannot_invite():
    state = make_state(0)

    result = invite(
        state,
        "alice@example.com",
    )

    assert result.ok is False
    assert result.reason == "no_seats_available"
    assert result.state.seats_used == 0
    assert result.state.members == {}

    assert_invariants(result.state)


@pytest.mark.parametrize(
    "state",
    [
        SeatState(
            seats_total=-1,
            seats_used=0,
            members={},
        ),
        SeatState(
            seats_total=5,
            seats_used=-1,
            members={},
        ),
        SeatState(
            seats_total=5,
            seats_used=6,
            members={},
        ),
        SeatState(
            seats_total=5,
            seats_used=0,
            members={"alice@example.com": "active"},
        ),
        SeatState(
            seats_total=5,
            seats_used=1,
            members={"alice@example.com": "unknown"},
        ),
        SeatState(
            seats_total=5,
            seats_used=1,
            members={"Alice@example.com": "active"},
        ),
    ],
)
def test_corrupted_state_is_rejected(state):
    with pytest.raises(ValueError):
        invite(state, "new@example.com")


def test_non_seat_state_is_rejected():
    with pytest.raises(TypeError):
        invite(None, "alice@example.com")


def test_realistic_sequence_is_idempotent():
    """
    Run the same logical operation sequence twice and prove that retries
    do not cause seat-count drift.
    """
    state = make_state(3)

    first_invite = invite(
        state,
        "alice@example.com",
    )
    state = first_invite.state

    first_activate = activate(
        state,
        "alice@example.com",
    )
    state = first_activate.state

    first_invite_bob = invite(
        state,
        "bob@example.com",
    )
    state = first_invite_bob.state

    first_cancel_bob = cancel_invite(
        state,
        "bob@example.com",
    )
    state = first_cancel_bob.state

    expected = state

    # Repeat the same calls as if the original requests had been retried.
    retry_invite_alice = invite(
        state,
        "alice@example.com",
    )
    state = retry_invite_alice.state

    retry_activate_alice = activate(
        state,
        "alice@example.com",
    )
    state = retry_activate_alice.state

    retry_invite_bob = invite(
        state,
        "bob@example.com",
    )
    state = retry_invite_bob.state

    retry_cancel_bob = cancel_invite(
        state,
        "bob@example.com",
    )
    state = retry_cancel_bob.state

    assert state.seats_used == expected.seats_used
    assert state.members == expected.members

    assert retry_invite_alice.reason == "already_member"
    assert retry_activate_alice.reason == "already_active"
    assert retry_invite_bob.reason == "ok"
    assert retry_cancel_bob.reason == "ok"

    assert_invariants(state)


def test_seat_result_is_frozen():
    result = invite(
        make_state(5),
        "alice@example.com",
    )

    with pytest.raises(AttributeError):
        result.ok = False