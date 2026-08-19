# Self Review

## Defect 1 ΓÇö Seat email case sensitivity

### Where
`backend/src/rbac/seats.py` ΓÇö email validation/member lookup

### What breaks
Email addresses are treated as case-sensitive.

Concrete example:

`invite("Bob@X.com")`
followed by
`invite("bob@x.com")`

can treat the same person as two different members and consume two seats.

### How bad
High severity. This can cause incorrect seat accounting and can deny a legitimate
user access because the organisation may incorrectly appear to have fewer seats
available.

### Fixed or not
Not fixed in this submission.

The correct fix is to normalize email addresses consistently, for example by
stripping whitespace and lowercasing before member lookup and storage.

---

## Defect 2 ΓÇö resolve_user_modules does not fail closed for None inputs

### Where
`backend/src/rbac/modules.py` ΓÇö `resolve_user_modules()`

### What breaks
Calling:

`resolve_user_modules(None, None)`

raises `TypeError` instead of failing closed.

The expected defensive behaviour for malformed or missing input is to return no
granted modules rather than allowing an exception to escape.

### How bad
Medium severity. A malformed authorization input can cause an unexpected
exception instead of a controlled authorization denial.

### Fixed or not
Not fixed in this submission.

This should be changed so missing or malformed inputs produce an empty module set
and, where appropriate, a warning rather than an exception.

---

## Defect 3 ΓÇö Dependencies are not declared for a clean checkout

### Where
Project root ΓÇö `requirements.txt`

### What breaks
The implementation uses external dependencies such as PyJWT and cryptography,
but a clean checkout does not have those dependencies declared in
`requirements.txt`.

A new developer or CI environment installing the project from scratch can
therefore fail before the RBAC tests can run.

### How bad
Medium severity. It can prevent the application and test suite from being
installed or executed in a clean environment.

### Fixed or not
Not fixed in this submission.

The dependencies should be declared with appropriate minimum or pinned versions
in `requirements.txt`.

---

## Defect 4 ΓÇö Offline cache cannot fully prevent rollback

### Where
`backend/src/rbac/offline_cache.py`

### What breaks
A user can save a genuinely valid sealed cache, allow the licence to expire, and
then restore the older sealed cache.

The HMAC still verifies because the old cache was genuinely signed.

### How bad
Security limitation. An older valid licence state can potentially be restored
on a machine whose owner can modify local files.

### Fixed or not
Not fully fixable with local file state alone.

The implementation detects modification, invalid signatures, malformed data, and
future-dated caches. It cannot determine that a previously valid signed cache has
since been superseded.

Preventing this completely would require trusted external state or
hardware-backed monotonic state.

---

## Least Confident About

I am least confident about the security boundary around locally stored licence
state. HMAC gives strong integrity protection against modification by someone who
does not know the signing secret, but it cannot provide complete anti-rollback
protection when the machine owner controls the filesystem. I have therefore
treated the offline cache as an integrity mechanism rather than claiming it solves
local licence enforcement completely. I am also least confident about legacy
interfaces from the previous day's modules where malformed inputs may still raise
exceptions instead of consistently failing closed.


## Day 4

### Defect 1 — HTTP authorization boundary is more complex than the underlying authorization logic

#### Where

`backend/src/rbac/api.py` — authorization endpoint and dependency/error handling.

#### What breaks

The underlying authorization functions return structured authorization decisions, but once exposed through HTTP there are additional failure paths: malformed headers, invalid tokens, unavailable JWKS state, invalid request bodies, and licence denials.

A future change to the endpoint can accidentally map these cases to the wrong HTTP status or expose internal failure information.

#### How bad

High severity. The API is now an untrusted network boundary. A wrong status code can cause clients to retry or refresh credentials incorrectly, while an overly detailed response can reveal internal authorization information.

#### Fixed or not

The current implementation has explicit tests for the important 401, 403, 422, 503, and response-redaction cases. However, this remains an area that needs regression tests whenever the endpoint or authorization dependency changes.

---

### Defect 2 — Migration correctness depends on preserving the idempotent state transition

#### Where

`backend/src/rbac/migration.py` — `migrate_record()` and `migrate_batch()`.

#### What breaks

Migration is safe only when an already-migrated record is treated as immutable with respect to its existing `project_id`.

For example:

```text
First migration:
record = {"sample_id": "s-1", "project_id": "project-a"}

Second migration with default_project_id="__unassigned__":
the existing project_id must remain "project-a"
```

If the migration logic were changed to blindly assign the default project on every invocation, a second run after a partial migration could silently move already-migrated records to the default project.

#### How bad

High severity. This is a data-integrity problem. A migration can appear successful while silently changing the ownership/scope of existing records.

#### Fixed or not

The current implementation and tests enforce the no-op behaviour for already-migrated records and verify that running the batch again produces the same result. The property should remain protected by regression tests because this is the most important invariant in a re-runnable migration.

---

### Least Confident About

I am least confident about the behaviour of the complete system during the transition between the old and new data shapes. The migration functions themselves are pure and tested, but a real production migration also depends on how callers interpret records that do not yet contain `project_id`. The code needs a clear operational decision about whether those records are treated as unassigned or temporarily visible during the migration window. The implementation documents and tests a decision, but this is the area I would validate with the system owner before production use.

I am also conscious that Task 17 introduced a public HTTP boundary around logic that was previously pure Python. The unit tests give good confidence in the explicitly tested status-code and error-response cases, but integration behaviour under the actual deployment stack would deserve additional verification.

---

### Second Pair of Eyes Before Production

Of today's three tasks, I would want a second pair of eyes on **Task 17 — the HTTP authorization API**.

Task 18 is already specifically a code-review exercise, and Task 19 has strong tests around idempotency, malformed records, partial migration, and scoped reads. Task 17 is the one I would review again before production because it is the point where trusted internal authorization logic becomes reachable through an untrusted network boundary.

In particular, I would have another engineer verify:

* authentication failures remain `401`;
* valid authentication with a denied licence remains `403`;
* unavailable JWKS state remains `503`;
* malformed request data remains `422`;
* error responses do not expose internal reasons, provider details, or tokens;
* the health endpoint remains independent of authorization dependencies.

That second review would provide confidence that the security properties of the underlying authorization functions have not been weakened by the HTTP layer.




## Day 5 — Self Review

### Task Reviewed

Optional Sample Migration / Project Scoping Migration

---

### Defect 1 — Existing project ownership could be overwritten

#### Where

`backend/src/rbac/sample_migration.py`

#### What breaks

A migration must not replace an existing valid `project_id` with the
migration's default project.

For example, if a sample already belongs to `project-a`, running the
migration with `default_project_id="__unassigned__"` must not move that
sample to `__unassigned__`.

#### Severity

High.

Incorrect project assignment can result in samples appearing under the wrong
project and can create a data-isolation problem.

#### Fixed or not

Fixed.

The migration preserves an existing valid `project_id` and only assigns the
default project when the project assignment is missing or invalid.

Regression tests verify that repeated migration runs do not reassign existing
project ownership.

---

### Defect 2 — One malformed row could stop the complete migration

#### Where

`backend/src/rbac/sample_migration.py`

#### What breaks

A malformed record in a large migration batch should not prevent all other
valid records from being migrated.

#### Severity

High for large production datasets.

A single invalid record could otherwise stop the migration and leave many valid
records partially migrated.

#### Fixed or not

Fixed.

`migrate_rows()` isolates failures at the individual-row level, records the
failure, and continues processing the remaining rows.

The migration result reports migrated, skipped, and failed records together
with row-specific error information.

---

### Defect 3 — Migration must be resumable and idempotent

#### Where

`backend/src/rbac/sample_migration.py`

#### What breaks

An interrupted migration may be executed again.

Already-migrated records must not be changed, while partially migrated records
must remain eligible for the next migration pass.

#### Severity

High.

A non-idempotent migration could repeatedly modify data or overwrite project
assignments during retries.

#### Fixed or not

Fixed.

The migration checks both `project_id` and `schema_version` before deciding
whether a row needs migration.

Already-current rows are skipped, while partially migrated rows can be
processed again.

Tests verify repeated execution and partial migration recovery.

---

### Defect 4 — Future schema versions must not be silently downgraded

#### Where

`backend/src/rbac/sample_migration.py`

#### What breaks

A row containing a schema version newer than the version understood by the
current migration must not be rewritten using older migration logic.

#### Severity

High.

Silently processing a future schema could cause data corruption or loss of
fields introduced by a newer application version.

#### Fixed or not

Fixed.

Rows with a schema version newer than the supported `SCHEMA_VERSION` are
rejected rather than silently downgraded.

---

### Defect 5 — Migration must not mutate caller-owned input data

#### Where

`backend/src/rbac/sample_migration.py`

#### What breaks

Mutating input rows directly could cause unexpected side effects for callers,
retry logic, logging, or other processing stages using the same objects.

#### Severity

Medium.

Unexpected mutation can make migration behavior difficult to reason about and
can introduce subtle retry bugs.

#### Fixed or not

Fixed.

The migration returns copied dictionaries and leaves the original input rows
unchanged.

Tests explicitly verify that the input collection and its dictionaries are not
mutated.

---

### Defect 6 — Unassigned samples need explicit migration-window behavior

#### Where

`backend/src/rbac/sample_migration.py`

#### What breaks

During migration, some samples may not yet have a valid `project_id`.

If these samples are immediately hidden, users may interpret the incomplete
migration as data loss. If they are incorrectly assigned to another project,
data isolation can be violated.

#### Severity

High.

Incorrect scoping can cause either apparent data loss or cross-project data
exposure.

#### Fixed or not

Addressed.

Missing or invalid project assignments are treated as `UNASSIGNED`.

`scoped_sample_filter()` supports migration-window visibility of unassigned
samples while also allowing strict project-only filtering when
`include_unassigned=False`.

---

### Least Confident About

I am least confident about the production database integration and concurrency
boundary of the migration.

The migration functions operate on the snapshot of rows supplied to them.
They cannot automatically account for rows inserted after that snapshot was
obtained.

The implementation therefore does not claim that newly inserted rows are
automatically migrated. A subsequent migration pass is required.

Before production use, the persistence-layer implementation should be reviewed
for:

- concurrent inserts;
- concurrent updates;
- transaction boundaries;
- retry behavior;
- atomic writes;
- migration completion detection;
- handling of rows that change while migration is running.

The migration logic itself has strong unit-test coverage, but these
database-level behaviors depend on the actual production persistence layer.

---

### Second Pair of Eyes Before Production

I would want another engineer to review the migration before production,
especially:

- preservation of existing `project_id`;
- idempotent and resumable behavior;
- malformed-row handling;
- future schema-version handling;
- unassigned-row visibility;
- concurrent inserts and updates;
- database transaction and atomicity behavior.

The current tests provide strong coverage of the migration logic and edge
cases, but production database behavior should receive a separate review.

