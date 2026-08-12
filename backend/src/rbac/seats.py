"""
Pure seat-allocation business rules.

An organization purchases a fixed number of seats. A member consumes a
seat as soon as they are invited, while their status is "pending". Once
activated, the member remains associated with the same seat.

The functions in this module never mutate the supplied SeatState. Every
operation returns a new SeatState.

The invariants are:

1. 0 <= seats_used <= seats_total
2. seats_used == len(members)
3. The input SeatState is never mutated.
4. Repeating an operation does not cause seat-count drift.
"""

from dataclasses import dataclass


_PENDING = "pending"
_ACTIVE = "active"

_VALID_MEMBER_STATUSES = frozenset({_PENDING, _ACTIVE})

_REASON_OK = "ok"
_REASON_NO_SEATS = "no_seats_available"
_REASON_ALREADY_MEMBER = "already_member"
_REASON_NOT_MEMBER = "not_a_member"
_REASON_ALREADY_ACTIVE = "already_active"
_REASON_NO_CHANGE = "no_change"


@dataclass(frozen=True)
class SeatState:
    seats_total: int
    seats_used: int
    members: dict[str, str]


@dataclass(frozen=True)
class SeatResult:
    state: SeatState
    ok: bool
    reason: str


def _validate_email(email: str) -> str:
    """
    Validate and normalize an email identifier.

    We intentionally do not attempt full RFC email validation here because
    this module is responsible for seat allocation, not email verification.
    """
    if not isinstance(email, str):
        raise ValueError("email must be a string")

    normalized = email.strip()

    if not normalized:
        raise ValueError("email must not be empty")

    return normalized


def _validate_state(state: SeatState) -> None:
    """
    Validate the state before performing an operation.

    Invalid state is rejected rather than silently repaired. Silently
    repairing a corrupted seat state could hide data corruption and make
    seat accounting unreliable.
    """
    if not isinstance(state, SeatState):
        raise TypeError("state must be a SeatState")

    if (
        isinstance(state.seats_total, bool)
        or not isinstance(state.seats_total, int)
    ):
        raise ValueError("seats_total must be a non-negative integer")

    if state.seats_total < 0:
        raise ValueError("seats_total must be a non-negative integer")

    if (
        isinstance(state.seats_used, bool)
        or not isinstance(state.seats_used, int)
    ):
        raise ValueError("seats_used must be a non-negative integer")

    if not isinstance(state.members, dict):
        raise ValueError("members must be a dictionary")

    if not 0 <= state.seats_used <= state.seats_total:
        raise ValueError("seat count invariant violated")

    if state.seats_used != len(state.members):
        raise ValueError("seats_used must equal the number of members")

    for email, status in state.members.items():
        if not isinstance(email, str) or not email.strip():
            raise ValueError("member emails must be non-empty strings")

        if status not in _VALID_MEMBER_STATUSES:
            raise ValueError(
                f"invalid member status for {email!r}: {status!r}"
            )


def _copy_state(
    state: SeatState,
    *,
    seats_used: int | None = None,
    members: dict[str, str] | None = None,
) -> SeatState:
    """
    Create a new SeatState without sharing the mutable members dictionary.
    """
    new_members = dict(state.members) if members is None else dict(members)

    new_seats_used = (
        state.seats_used
        if seats_used is None
        else seats_used
    )

    new_state = SeatState(
        seats_total=state.seats_total,
        seats_used=new_seats_used,
        members=new_members,
    )

    _validate_state(new_state)

    return new_state


def invite(state: SeatState, email: str) -> SeatResult:
    """
    Reserve one seat and add an invited member as pending.

    If the email already exists, the operation is idempotent and does not
    consume another seat.

    If no seats remain, the input state is preserved and the operation
    returns no_seats_available.
    """
    _validate_state(state)
    email = _validate_email(email)

    if email in state.members:
        return SeatResult(
            state=_copy_state(state),
            ok=False,
            reason=_REASON_ALREADY_MEMBER,
        )

    if state.seats_used >= state.seats_total:
        return SeatResult(
            state=_copy_state(state),
            ok=False,
            reason=_REASON_NO_SEATS,
        )

    members = dict(state.members)
    members[email] = _PENDING

    new_state = _copy_state(
        state,
        seats_used=state.seats_used + 1,
        members=members,
    )

    return SeatResult(
        state=new_state,
        ok=True,
        reason=_REASON_OK,
    )


def activate(state: SeatState, email: str) -> SeatResult:
    """
    Activate a pending member.

    Activation consumes no additional seat because the seat was already
    reserved when the invitation was created.

    Re-activating an active member is idempotent.
    """
    _validate_state(state)
    email = _validate_email(email)

    current_status = state.members.get(email)

    if current_status is None:
        return SeatResult(
            state=_copy_state(state),
            ok=False,
            reason=_REASON_NOT_MEMBER,
        )

    if current_status == _ACTIVE:
        return SeatResult(
            state=_copy_state(state),
            ok=False,
            reason=_REASON_ALREADY_ACTIVE,
        )

    members = dict(state.members)
    members[email] = _ACTIVE

    new_state = _copy_state(
        state,
        seats_used=state.seats_used,
        members=members,
    )

    return SeatResult(
        state=new_state,
        ok=True,
        reason=_REASON_OK,
    )


def cancel_invite(state: SeatState, email: str) -> SeatResult:
    """
    Cancel a pending invitation and release its reserved seat.

    Cancelling an unknown member is a no-op and cannot make seats_used
    negative.

    Cancelling an active member is also a no-op because an active member
    must be removed through deactivate().
    """
    _validate_state(state)
    email = _validate_email(email)

    current_status = state.members.get(email)

    if current_status is None:
        return SeatResult(
            state=_copy_state(state),
            ok=False,
            reason=_REASON_NOT_MEMBER,
        )

    if current_status != _PENDING:
        return SeatResult(
            state=_copy_state(state),
            ok=False,
            reason=_REASON_NO_CHANGE,
        )

    members = dict(state.members)
    del members[email]

    new_state = _copy_state(
        state,
        seats_used=state.seats_used - 1,
        members=members,
    )

    return SeatResult(
        state=new_state,
        ok=True,
        reason=_REASON_OK,
    )


def deactivate(state: SeatState, email: str) -> SeatResult:
    """
    Remove an active member and release their seat.

    Deactivating the same member twice is idempotent: the first operation
    releases exactly one seat, while the second returns not_a_member and
    cannot release another seat.

    A pending invitation is not deactivated; it should be cancelled with
    cancel_invite().
    """
    _validate_state(state)
    email = _validate_email(email)

    current_status = state.members.get(email)

    if current_status is None:
        return SeatResult(
            state=_copy_state(state),
            ok=False,
            reason=_REASON_NOT_MEMBER,
        )

    if current_status != _ACTIVE:
        return SeatResult(
            state=_copy_state(state),
            ok=False,
            reason=_REASON_NO_CHANGE,
        )

    members = dict(state.members)
    del members[email]

    new_state = _copy_state(
        state,
        seats_used=state.seats_used - 1,
        members=members,
    )

    return SeatResult(
        state=new_state,
        ok=True,
        reason=_REASON_OK,
    )