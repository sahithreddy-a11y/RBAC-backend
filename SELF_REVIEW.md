# Self Review

## 1. Task 12 — JWKS cache failure behaviour

### Where
`backend/src/rbac/jwks_cache.py`

### What breaks
When the JWKS fetcher fails after the cached data becomes stale, the cache must follow
the explicitly chosen stale-cache policy. A stale key can remain trusted longer than
intended if stale data is served without a bound.

### How bad
Security impact: an old signing key may continue to be trusted after the identity
provider has stopped publishing it.

### Fixed or not
The behaviour is documented in `NOTES.md` and is bounded according to the chosen
availability/security policy.

---

## 2. Task 13 — Concurrent seat allocation

### Where
`backend/src/rbac/seat_store.py`

### What breaks
Two callers can read the same seat-store version. Only the first caller should be
allowed to commit that version. If the second caller were allowed to commit using the
stale version, both operations could consume the same remaining seat.

### How bad
High severity: this could oversell an organisation's licensed seats and corrupt the
seat count.

### Fixed or not
Fixed using optimistic concurrency control. A commit succeeds only when the supplied
expected version still matches the stored version. A stale caller receives
`version_conflict` and must re-read before retrying.

---

## 3. Task 14 — Token claims and licence state

### Where
`backend/src/rbac/token_claims.py`

### What breaks
A token must not retain previously granted modules when the organisation's licence
has expired or been revoked. If the stored user module list were copied directly into
the token, a user could retain access after the licence became invalid.

### How bad
High severity: an expired or revoked licence could still grant access to protected
modules.

### Fixed or not
Fixed by evaluating the licence at token creation time and resolving modules through
the existing `resolve_user_modules()` logic. Expired or revoked licences produce an
empty module set.

---

## Task 4 — Offline cache rollback limitation

### Where
`backend/src/rbac/offline_cache.py`

### What breaks
A previously valid cache can be copied back after a licence has expired. Its HMAC is
still valid because it was genuinely issued and signed by the trusted issuer.

### How bad
Security limitation: local rollback can potentially restore an older valid licence
state.

### Fixed or not
Not fully fixable with local file state alone. A machine owner who can modify files
can restore an older valid cache. Preventing this completely requires trusted external
state or hardware-backed monotonic storage.

The implementation does reject modified data, invalid signatures, malformed caches,
and future-dated caches. It therefore provides integrity protection but not complete
anti-rollback protection.

---

## Least Confident About

I am least confident about the boundaries between locally enforceable security and
security that requires trusted external state. The offline cache can reliably detect
tampering because the HMAC protects the serialized data, but it cannot prove that an
older genuinely signed cache has been superseded. Similarly, cache and licence
decisions depend on the correctness of the injected time value. These limitations are
documented rather than hidden, and the implementation fails closed for malformed or
invalidly signed data.