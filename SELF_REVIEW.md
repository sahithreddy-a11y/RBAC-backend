# Self Review

## Defect 1 — Seat email case sensitivity

### Where
`backend/src/rbac/seats.py` — email validation/member lookup

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

## Defect 2 — resolve_user_modules does not fail closed for None inputs

### Where
`backend/src/rbac/modules.py` — `resolve_user_modules()`

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

## Defect 3 — Dependencies are not declared for a clean checkout

### Where
Project root — `requirements.txt`

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

## Defect 4 — Offline cache cannot fully prevent rollback

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