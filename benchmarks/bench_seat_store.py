from __future__ import annotations

import time
from collections import Counter, deque
from statistics import mean

from backend.src.rbac.seat_store import SeatStore, VersionedSeatState
from backend.src.rbac.seats import SeatState


# ------------------------------------------------------------
# Benchmark configuration
# ------------------------------------------------------------

TOTAL_OPERATIONS = 10_000

SUCCESS_COUNT = 7_000
CONFLICT_COUNT = 2_000
REPLAY_COUNT = 1_000

SEAT_CAPACITY = SUCCESS_COUNT + 100

# SeatStore keeps at most 1,000 completed request IDs.
# We only replay IDs from this recent window.
REPLAY_WINDOW = SeatStore.REQUEST_ID_LIMIT


# ------------------------------------------------------------
# State creation
# ------------------------------------------------------------

def make_initial_state() -> VersionedSeatState:
    return VersionedSeatState(
        state=SeatState(
            seats_total=SEAT_CAPACITY,
            seats_used=0,
            members={},
        ),
        version=0,
    )


# ------------------------------------------------------------
# Workload creation
# ------------------------------------------------------------

def build_workload() -> list[str]:
    """
    Create a deterministic 10,000-operation workload.

    Pattern:
        success
        conflict
        replay

    repeated according to the requested 70/20/10 distribution.

    This keeps the workload interleaved instead of executing all
    successful commits first, followed by conflicts and replays.
    """

    workload: list[str] = []

    remaining = {
        "success": SUCCESS_COUNT,
        "conflict": CONFLICT_COUNT,
        "replay": REPLAY_COUNT,
    }

    # Deterministic repeating pattern gives:
    # 7 success, 2 conflict, 1 replay
    pattern = (
        "success",
        "success",
        "success",
        "success",
        "success",
        "success",
        "success",
        "conflict",
        "conflict",
        "replay",
    )

    while len(workload) < TOTAL_OPERATIONS:
        for operation_type in pattern:
            if remaining[operation_type] > 0:
                workload.append(operation_type)
                remaining[operation_type] -= 1

            if len(workload) == TOTAL_OPERATIONS:
                break

    return workload


# ------------------------------------------------------------
# Statistics helpers
# ------------------------------------------------------------

def percentile(values: list[int], percentage: float) -> float:
    """
    Calculate a percentile from timing values stored in nanoseconds.
    """

    if not values:
        return 0.0

    ordered = sorted(values)

    index = (len(ordered) - 1) * percentage
    lower = int(index)
    upper = min(lower + 1, len(ordered) - 1)

    fraction = index - lower

    return ordered[lower] + (
        ordered[upper] - ordered[lower]
    ) * fraction


def format_duration(nanoseconds: float) -> str:
    return f"{nanoseconds / 1_000_000:.3f} ms"


# ------------------------------------------------------------
# Benchmark
# ------------------------------------------------------------

def run_benchmark() -> None:
    workload = build_workload()

    if len(workload) != TOTAL_OPERATIONS:
        raise RuntimeError(
            f"Workload contains {len(workload)} operations; "
            f"expected {TOTAL_OPERATIONS}"
        )

    if workload.count("success") != SUCCESS_COUNT:
        raise RuntimeError("Success workload count is incorrect")

    if workload.count("conflict") != CONFLICT_COUNT:
        raise RuntimeError("Conflict workload count is incorrect")

    if workload.count("replay") != REPLAY_COUNT:
        raise RuntimeError("Replay workload count is incorrect")

    store = SeatStore(make_initial_state())

    counters = Counter()

    # Store individual operation durations so that we can calculate
    # average and p95 latency for each operation category.
    timings: dict[str, list[int]] = {
        "success": [],
        "conflict": [],
        "replay": [],
    }

    # Keep only recent successful requests.
    #
    # This mirrors SeatStore's bounded request-ID cache and guarantees
    # that replay operations use request IDs that should still exist.
    recent_successful_requests: deque[
        tuple[str, str, int]
    ] = deque(maxlen=REPLAY_WINDOW)

    current_version = 0
    success_index = 0
    replay_index = 0

    # --------------------------------------------------------
    # Start benchmark
    # --------------------------------------------------------

    benchmark_start = time.perf_counter_ns()

    for operation_type in workload:

        # ----------------------------------------------------
        # Successful commit
        # ----------------------------------------------------

        if operation_type == "success":
            request_id = f"success-{success_index}"
            email = f"user-{success_index}@example.com"

            start = time.perf_counter_ns()

            result = store.commit(
                current_version,
                "invite",
                email,
                request_id=request_id,
            )

            elapsed = time.perf_counter_ns() - start

            timings["success"].append(elapsed)
            counters["success_attempts"] += 1

            if not result.ok or result.reason != "ok":
                raise RuntimeError(
                    "Expected successful commit, got "
                    f"ok={result.ok}, reason={result.reason}"
                )

            # A successful commit increments the version by exactly one.
            current_version = result.state.version

            # Keep this request available for replay testing.
            recent_successful_requests.append(
                (request_id, email, current_version)
            )

            success_index += 1

        # ----------------------------------------------------
        # Version conflict
        # ----------------------------------------------------

        elif operation_type == "conflict":
            conflict_index = counters["conflict_attempts"]

            request_id = f"conflict-{conflict_index}"
            email = f"conflict-{conflict_index}@example.com"

            # Use a stale version.
            #
            # The current store is at current_version, while the
            # submitted version is deliberately one version behind.
            stale_version = max(0, current_version - 1)

            start = time.perf_counter_ns()

            result = store.commit(
                stale_version,
                "invite",
                email,
                request_id=request_id,
            )

            elapsed = time.perf_counter_ns() - start

            timings["conflict"].append(elapsed)
            counters["conflict_attempts"] += 1

            if result.ok or result.reason != "version_conflict":
                raise RuntimeError(
                    "Expected version conflict, got "
                    f"ok={result.ok}, reason={result.reason}"
                )

            # A conflict must not change the store version.
            if result.state.version != current_version:
                raise RuntimeError(
                    "Version conflict unexpectedly changed the version"
                )

        # ----------------------------------------------------
        # Replay
        # ----------------------------------------------------

        elif operation_type == "replay":
            if not recent_successful_requests:
                raise RuntimeError(
                    "Replay requested before any successful request existed"
                )

            # Select a request from the recent successful window.
            #
            # Because the deque is limited to REQUEST_ID_LIMIT,
            # these IDs are kept aligned with SeatStore's bounded
            # idempotency cache.
            replay_position = (
                replay_index % len(recent_successful_requests)
            )

            request_id, email, original_version = (
                recent_successful_requests[replay_position]
            )

            replay_index += 1

            # Deliberately provide an incorrect version.
            #
            # SeatStore checks request_id first, so a valid replay
            # must still return duplicate_request.
            intentionally_wrong_version = 999_999

            start = time.perf_counter_ns()

            result = store.commit(
                intentionally_wrong_version,
                "invite",
                email,
                request_id=request_id,
            )

            elapsed = time.perf_counter_ns() - start

            timings["replay"].append(elapsed)
            counters["replay_attempts"] += 1

            if not result.ok or result.reason != "duplicate_request":
                raise RuntimeError(
                    "Expected duplicate request, got "
                    f"ok={result.ok}, reason={result.reason}"
                )

            # A replay must return the original committed state.
            if result.state.version != original_version:
                raise RuntimeError(
                    "Replay returned an unexpected version"
                )

        else:
            raise RuntimeError(
                f"Unknown benchmark operation: {operation_type}"
            )

    total_elapsed_ns = time.perf_counter_ns() - benchmark_start

    total_elapsed_seconds = total_elapsed_ns / 1_000_000_000

    total_attempts = (
        counters["success_attempts"]
        + counters["conflict_attempts"]
        + counters["replay_attempts"]
    )

    throughput = total_attempts / total_elapsed_seconds

    # --------------------------------------------------------
    # Validate final state
    # --------------------------------------------------------

    final_state = store.read()

    expected_version = SUCCESS_COUNT
    expected_seats_used = SUCCESS_COUNT

    if final_state.version != expected_version:
        raise RuntimeError(
            f"Unexpected final version: {final_state.version}; "
            f"expected {expected_version}"
        )

    if final_state.state.seats_used != expected_seats_used:
        raise RuntimeError(
            f"Unexpected seats_used: "
            f"{final_state.state.seats_used}; "
            f"expected {expected_seats_used}"
        )

    if len(store._completed_requests) != REPLAY_WINDOW:
        raise RuntimeError(
            f"Unexpected request cache size: "
            f"{len(store._completed_requests)}; "
            f"expected {REPLAY_WINDOW}"
        )

    # --------------------------------------------------------
    # Report
    # --------------------------------------------------------

    print()
    print("=" * 72)
    print("SeatStore Benchmark")
    print("=" * 72)

    print()
    print("Workload")
    print("-" * 72)
    print(f"Total operations:       {total_attempts:,}")
    print(
        f"Successful commits:     "
        f"{counters['success_attempts']:,}"
    )
    print(
        f"Version conflicts:      "
        f"{counters['conflict_attempts']:,}"
    )
    print(
        f"Replays:                "
        f"{counters['replay_attempts']:,}"
    )

    print()
    print("Throughput")
    print("-" * 72)
    print(
        f"Total benchmark time:   "
        f"{total_elapsed_seconds:.6f} seconds"
    )
    print(
        f"Throughput:             "
        f"{throughput:,.2f} operations/sec"
    )

    print()
    print("Where the time goes")
    print("-" * 72)

    total_timed_operation_ns = sum(
        sum(values)
        for values in timings.values()
    )

    for operation_type in ("success", "conflict", "replay"):
        values = timings[operation_type]

        total_ns = sum(values)

        percentage = (
            total_ns / total_timed_operation_ns * 100
            if total_timed_operation_ns
            else 0
        )

        average_ns = mean(values) if values else 0
        p95_ns = percentile(values, 0.95)

        print(
            f"{operation_type.capitalize():20}"
            f"{len(values):>8,} ops   "
            f"{format_duration(total_ns):>12}   "
            f"{percentage:>6.2f}%"
        )

        print(
            f"{'':20}"
            f"Average: {format_duration(average_ns):>12}   "
            f"P95: {format_duration(p95_ns):>12}"
        )

    print()
    print("Final state validation")
    print("-" * 72)
    print(f"Final version:         {final_state.version:,}")
    print(f"Seats used:            {final_state.state.seats_used:,}")
    print(f"Seats total:           {final_state.state.seats_total:,}")
    print(
        f"Completed request IDs: "
        f"{len(store._completed_requests):,}"
    )

    print()
    print("Benchmark conclusion")
    print("-" * 72)
    print(
        "The benchmark measures the existing SeatStore implementation "
        "without changing its behavior."
    )
    print(
        "Optimization decisions should be based on the measured "
        "time breakdown and latency results."
    )

    print("=" * 72)
    print()


if __name__ == "__main__":
    run_benchmark()