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

## Day 6 — Self Review

### Task Reviewed

Task 25 — Code Review
Task 26 — Production Sample Backfill
Task 27 — Locked-Tile View Model

---

### Task 25 — Code Review

#### Defect 1 — Authorization input can fail open or expose unintended behaviour

##### Where

`day4_review_target.py` — entitlement/authorization decision logic identified during the code review.

##### What breaks

Malformed or unexpected authorization inputs can cause the entitlement decision to behave differently from the intended fail-closed policy.

The important risk is that authorization code must not assume that callers always provide valid claims or correctly shaped data.

##### How bad

High severity.

Authorization failures can affect whether a user is allowed to access protected functionality. Unexpected input should result in a controlled denial rather than an exception or an unintended grant.

##### Fixed or not

Not fixed in the reviewed code.

The review finding was documented in `CODE_REVIEW.md`; the task was to identify and communicate the defects rather than modify the author's implementation.

---

### Task 26 — Production Sample Backfill

#### Defect 1 — Legacy `"Unknown"` treatment value requires explicit normalization

##### Where

`backend/src/rbac/sample_backfill.py` — `normalize_legacy_values()`.

##### What breaks

Older rows use the literal string `"Unknown"` for `treatment`, while newer rows use `NULL` for the same "not recorded" state.

Keeping both representations would make filtering and downstream logic inconsistent.

##### How bad

Medium severity.

The data would remain readable, but different representations of the same semantic state could produce inconsistent filtering, reporting, and application behaviour.

##### Fixed or not

Fixed.

The backfill normalizes the legacy `"Unknown"` placeholder to `None`. This treats `"Unknown"` as "not recorded" rather than as a real treatment value.

This is an intentional data-normalization decision rather than silently treating `"Unknown"` as a meaningful treatment.

A user who previously filtered specifically for `"Unknown"` would need to use the application's "not recorded"/null representation after the backfill.

---

#### Defect 2 — Checkpointing cannot depend on row indexes

##### Where

`backend/src/rbac/sample_backfill.py` — `run_backfill()` checkpoint handling.

##### What breaks

A checkpoint such as "processed through index 40,000" is unsafe because rows can be inserted between runs.

The same index can refer to a different row after the dataset changes, causing rows to be skipped or processed incorrectly.

##### How bad

High severity.

A faulty resume mechanism can silently leave production rows unmigrated or process the wrong rows.

##### Fixed or not

Fixed.

The checkpoint uses a stable row identity rather than relying only on the position of a row in the input list.

A checkpoint is associated with its own backfill run, and stale or foreign checkpoint information is rejected rather than blindly trusted.

---

#### Defect 3 — Ownership can change while the backfill is running

##### Where

`backend/src/rbac/sample_backfill.py` — `run_backfill()` and migration processing.

##### What breaks

A startup job can assign a `user_id` to a row after the backfill has already processed that row.

The migration therefore operates on the snapshot it observed; it cannot claim that the result reflects every ownership change that happened after that snapshot.

##### How bad

High severity for production consistency.

Without a clear policy, a long-running migration could leave ownership-related state inconsistent with the latest database state.

##### Fixed or not

Addressed.

The backfill treats each invocation as operating on the rows observed by that pass. Ownership changes occurring afterwards are not silently assumed to have been processed.

A subsequent pass over the current rows is required to reconcile changes that happened between passes.

This makes the concurrency boundary explicit instead of pretending that a snapshot-based migration has live database knowledge.

---

### Task 27 — Locked-Tile View Model

#### Defect 1 — Licensed and installed are separate states

##### Where

`js/tile_view_model.js` — tile action selection.

##### What breaks

A licensed module that is already installed should launch, while a licensed module that is not installed should offer installation.

Installation state must not be treated as entitlement.

##### How bad

High severity.

Confusing installation with licensing could allow an installed but unlicensed module to become usable.

##### Fixed or not

Fixed.

The view model checks entitlement independently from `installedSkus`.

Licensed + installed produces `launch`.

Licensed + not installed produces `install`.

Unlicensed modules remain visible and use `contact_sales`.

---

#### Defect 2 — Expired licences need a different user-facing reason

##### Where

`js/tile_view_model.js` — entitlement reason to tooltip mapping.

##### What breaks

An expired licence must not be presented as though the user never owned the module.

The renderer needs to distinguish an expired entitlement from a never-licensed entitlement.

##### How bad

Medium severity.

This does not grant unauthorized access, but it gives the user incorrect information and makes the UI less useful for diagnosing licence problems.

##### Fixed or not

Fixed.

The view model maps the expired reason to a dedicated expiry tooltip while never-licensed modules receive the appropriate unlicensed tooltip.

---

#### Defect 3 — `cross_compare` has a separate dependency reason

##### Where

`js/tile_view_model.js` — `cross_compare` reason handling.

##### What breaks

`cross_compare` can be owned but still unusable when fewer than two base modules are available.

It must not be reported simply as "not licensed" because the user may actually have the entitlement.

##### How bad

Medium severity.

The wrong explanation can make a valid entitlement look broken and can cause users to contact support unnecessarily.

##### Fixed or not

Fixed.

The `requires_two_base_modules` reason has its own tooltip explaining that a second base module is required.

---

### Least Confident About

I am least confident about the production boundaries around Task 26.

The migration logic has strong coverage for validation, idempotency, partial failures, resume behaviour, legacy-value normalization, and ownership changes between passes. However, the real production database can have concurrent inserts and updates that are outside the snapshot supplied to the migration.

The important operational assumption is that one backfill pass only guarantees correctness for the rows it observed. A later pass is required to reconcile rows that change or arrive after that snapshot.

I would therefore want the persistence-layer transaction boundaries and the mechanism that obtains and writes the production rows reviewed before treating the migration as completely production-safe.

I am also least confident about the user-facing impact of converting legacy `"Unknown"` treatment values to `NULL`. The normalization is semantically consistent with the current data model, but existing users or reports that explicitly filter for `"Unknown"` need to understand that those rows will now appear under the "not recorded" representation.

---

### Second Pair of Eyes Before Production

I would want another engineer to review **Task 26 — the production backfill** before it runs against the live table.

In particular, I would verify:

* the checkpoint cannot accidentally resume the wrong run;
* stale or foreign checkpoints are rejected safely;
* concurrent ownership changes are handled by a subsequent pass;
* existing project ownership is never overwritten;
* malformed rows cannot stop the complete backfill;
* legacy `"Unknown"` values are intentionally converted to `NULL`;
* the database transaction and write boundaries are safe.

Task 27 also deserves a quick renderer-level review to confirm that every entitlement reason produced by Task 23 has exactly one useful tooltip and that malformed claims always result in a locked tile rather than an exception.
