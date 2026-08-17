from collections import OrderedDict
from dataclasses import dataclass

from backend.src.rbac.seats import (
    SeatState,
    activate,
    cancel_invite,
    deactivate,
    invite,
)


@dataclass(frozen=True)
class VersionedSeatState:
    state: SeatState
    version: int


@dataclass(frozen=True)
class CommitResult:
    state: VersionedSeatState
    ok: bool
    reason: str


class SeatStore:
    """
    In-memory stand-in for a DynamoDB item using optimistic concurrency.

    Successful commits increment the version by exactly one.

    Completed request IDs are stored in a bounded FIFO cache. When the
    cache exceeds REQUEST_ID_LIMIT, the oldest request is removed.
    """

    REQUEST_ID_LIMIT = 1000

    def __init__(self, initial: VersionedSeatState) -> None:
        if not isinstance(initial, VersionedSeatState):
            raise TypeError("initial must be a VersionedSeatState")

        if not isinstance(initial.version, int) or isinstance(
            initial.version, bool
        ):
            raise ValueError("version must be an integer")

        if initial.version < 0:
            raise ValueError("version must be non-negative")

        self._state = initial
        self._completed_requests: OrderedDict[
            str, CommitResult
        ] = OrderedDict()

    def read(self) -> VersionedSeatState:
        state = self._state.state

        copied_state = SeatState(
            seats_total=state.seats_total,
            seats_used=state.seats_used,
            members=dict(state.members),
        )

        return VersionedSeatState(
            state=copied_state,
            version=self._state.version,
        )

    def commit(
        self,
        expected_version: int,
        operation: str,
        email: str,
        *,
        request_id: str,
    ) -> CommitResult:
        if not isinstance(expected_version, int) or isinstance(
            expected_version, bool
        ):
            raise ValueError("expected_version must be an integer")

        if not isinstance(request_id, str) or not request_id:
            raise ValueError("request_id must be a non-empty string")

        # Idempotency check comes before version checking so that
        # replaying a completed request always returns its original result.
        if request_id in self._completed_requests:
            original = self._completed_requests[request_id]

            return CommitResult(
                state=original.state,
                ok=original.ok,
                reason="duplicate_request",
            )

        # Optimistic concurrency check.
        if expected_version != self._state.version:
            return CommitResult(
                state=self._state,
                ok=False,
                reason="version_conflict",
            )

        operations = {
            "invite": invite,
            "activate": activate,
            "cancel_invite": cancel_invite,
            "deactivate": deactivate,
        }

        operation_function = operations.get(operation)

        if operation_function is None:
            return CommitResult(
                state=self._state,
                ok=False,
                reason="unknown_operation",
            )

        # Reuse the existing Day 2 seat operation.
        result = operation_function(self._state.state, email)

        if not result.ok:
            return CommitResult(
                state=self._state,
                ok=False,
                reason=result.reason,
            )

        new_state = VersionedSeatState(
            state=result.state,
            version=self._state.version + 1,
        )

        committed = CommitResult(
            state=new_state,
            ok=True,
            reason="ok",
        )

        self._state = new_state

        # Store only completed successful requests for idempotent replay.
        self._completed_requests[request_id] = committed

        while len(self._completed_requests) > self.REQUEST_ID_LIMIT:
            self._completed_requests.popitem(last=False)

        return committed