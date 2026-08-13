# Self Review — Day 3

## Defect 1 — Seat state accepts non-canonical member email keys

### Where
`backend/src/rbac/seats.py`, lines 102–104, together with
`backend/src/rbac/seats.py`, lines 150–151.

### What breaks

`_validate_state()` checks that member email keys are non-empty strings, but it
does not require them to be in the canonical form produced by `_validate_email()`
(lowercase and stripped).

For example, this state is accepted:

```python
SeatState(
    seats_total=2,
    seats_used=1,
    members={"Alice@Example.com": "pending"},
)