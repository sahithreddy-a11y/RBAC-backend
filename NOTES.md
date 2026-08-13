# RBAC Permission Engine — Notes

## 1. Decisions

### Task 1 — Activation token

I used a cryptographically secure random source for generating activation tokens rather than a predictable pseudo-random source. The generated token uses the required uppercase/number format and is treated as case-sensitive. Tokens expire 48 hours after creation, and used or expired tokens are rejected. And also checked the uniqueness of 10000 generated tokens.

### Task 2 — License status

I treated a date-only expiry as valid through the entire stated calendar day. Therefore, a license with an expiry date of today remains valid until the end of that day. Revoked and suspended licenses remain invalid regardless of their future expiry date. Invalid date values fail closed.

### Task 3 — Module resolution

Licensed modules constrain the modules that can be granted to a user. Unknown modules are rejected, and known modules that are not included in the license are also rejected. The `cross_compare` module requires at least two granted base modules. Duplicate requests are collapsed and granted modules are returned in sorted order.

### Task 4 — Claims parsing

The claims parser accepts modules either as a comma-separated string or as a list and normalizes them into a clean list. Missing optional claims become `None`, missing roles default to `researcher`, and a missing `sub` claim raises `ValueError`.

The parser deliberately does not verify token signatures, issuers, or expiry. Signature verification must happen before the claims parser is called.

### Task 5 — Audit events

Sensitive metadata is redacted inside the audit-event builder rather than relying on every caller to sanitize its own data. This ensures sensitive values such as passwords, tokens, and authorization headers do not accidentally reach the audit record. Redaction is case-insensitive and works inside nested dictionaries.

---

## 2. Incomplete Work

All five coding tasks and their acceptance tests are implemented.

The assignment does not define a Task 6 or require a database-backed audit log. The current Task 5 implementation builds the audit event record as required.

---

## 3. Approximate Time

* Task 1 — Activation token handling: approximately 45 minutes
* Task 2 — License status evaluation: approximately 30 minutes
* Task 3 — Module resolution: approximately 30 minutes
* Task 4 — Claims parsing: approximately 45 minutes
* Task 5 — Audit event builder: approximately 30 minutes
* Testing, debugging, and review: approximately 45 minutes

---

## 4. Tools Used

* Python
* pytest
* Git
* PowerShell
* Visual Studio Code
* AI assistant (ChatGPT) for implementation guidance, test design, debugging, and explanation

I reviewed and tested the implementation rather than relying only on generated code. The final test suite passes all implemented tests.

---

## 5. Reasoning Questions

### 1. In Task 3, why must license_modules constrain requested_modules?

The license defines which modules the organization has actually purchased or is entitled to use. The user's requested modules can therefore only be granted when they are both known by the system and included in the license.

If the two lists were simply merged, a user or administrator could request a module that the organization did not license and receive access to it. That would bypass the licensing restriction and could expose functionality that the organization has not purchased.

### 2. In Task 4, why is it important that the parser does not verify the token's signature?

Parsing and verification are separate responsibilities. The claims parser only converts the claims contained in an already-verified token payload into a structured representation.

If someone assumed that parsing also verified the signature, they could trust claims from an untrusted or forged token. An attacker could potentially change values such as the user ID, role, organization, or licensed modules and gain unauthorized access.

### 3. In Task 2, why does a revoked licence stay invalid even when its expiry date is a year away?

Revocation is an explicit decision that the license should no longer be usable. Its future expiry date only describes when the license would normally expire; it does not override a revocation.

For example, if an organization's license is revoked because of a security or payment issue but the system only checks the expiry date, the organization could continue accessing licensed functionality for another year. That could allow unauthorized access after the license has been intentionally disabled.

### 4. In Task 5, why redact inside the builder rather than trusting each caller?

The audit builder is the central point where audit records are created. If each caller were responsible for removing sensitive information, one developer could easily forget to sanitize a password, token, or authorization header.

Redacting inside the builder creates a single security boundary. Every caller receives the same protection, including callers added later who may not know all of the audit logging security requirements.



### Task 6 — JWT verification

JWT verification is performed before trusting token claims. The verifier accepts only RS256 tokens, requires a known `kid`, validates the selected RSA signing key, verifies the signature, and checks the required `exp`, `iss`, and `aud` claims.

The `token_use` claim is also validated so that a token intended for another purpose cannot be accepted. Expired, not-yet-valid, malformed, incorrectly signed, wrong-issuer, wrong-audience, unknown-key, and unsupported-algorithm tokens fail safely without exposing cryptographic exceptions to callers.

### Task 7 — Session and offline grace handling

Session validation distinguishes between valid access tokens, expired access tokens, refresh-token age, and offline operation.

A valid access token can continue to work while offline. An expired access token can only continue during the defined seven-day offline grace period. After that period, reconnection is required.

Refresh tokens older than 30 days require login again. A future online-check timestamp is rejected rather than being trusted. Missing or invalid session timestamps fail safely, and naive datetimes are treated as UTC while timezone-aware datetimes are normalized to UTC.

### Task 8 — Seat management and idempotency

Seat management ensures that invitations cannot exceed the organization's available seat count.

Pending invitations reserve seats, activation converts a pending member into an active member without consuming an additional seat, and cancellation releases the reserved seat. Deactivation of an active member releases exactly one seat.

Duplicate invitations and repeated activation/deactivation operations are handled idempotently so that the same operation cannot accidentally consume or release multiple seats. Invalid emails, corrupted state, zero-seat organizations, and unknown members are rejected safely without unintended state changes.

### Task 9 — Authentication error mapping

Authentication-provider errors are converted into safe application-level responses rather than exposing provider-specific exception details to users.

Credential-related failures use safe, non-enumerating messages so that user existence is not revealed. Retryable errors provide retry/wait behavior where appropriate, while disabled accounts direct the user to contact an administrator.

Unknown and malformed error inputs fail safely using a generic fallback. Provider exception names and stack-trace information are never exposed in user-facing messages.

### Task 10 — Authorization pipeline

The authorization pipeline performs the security checks in the required order: token verification, claims parsing, license evaluation, and module resolution.

A failed verification or claims parsing step stops the pipeline immediately. An invalid license prevents module authorization, while a valid license allows the requested modules to be resolved against the license.

A single normalized UTC time is passed through the pipeline so that all time-based decisions use the same clock value. Invalid top-level inputs and invalid time values fail safely, and denied authorization results do not expose granted modules.

### Task 11 — Installer integrity and version checks

Installer integrity is verified using SHA-256. Files are processed incrementally in chunks so large installers do not need to be loaded entirely into memory.

The expected digest is validated before comparison, and `hmac.compare_digest` is used for the digest comparison. Missing, unreadable, or invalid inputs fail closed.

Version checks use numeric `MAJOR.MINOR.PATCH` comparison rather than string comparison, so versions such as `0.1.9` and `0.1.10` are ordered correctly. Malformed versions, negative values, leading-zero components, and incorrect version formats are rejected.

---

## 2. Incomplete Work

All coding tasks covered today and their acceptance tests are implemented.

The implementation was also tested against additional edge cases beyond the basic acceptance scenarios.

---

## 3. Approximate Time

- Task 6 — JWT verification: approximately 1 hour
- Task 7 — Session and offline grace handling: approximately 1 hour
- Task 8 — Seat management and idempotency: approximately 1 hour 30 minutes
- Task 9 — Authentication error mapping: approximately 1 hour
- Task 11 — Authorization pipeline: approximately 1 hour
- Task Addition — Installer integrity and version checks: approximately 1 hour
- Testing, debugging, edge-case handling, and review: approximately 1 hour 30 minutes

---

## 4. Tools Used

- Python
- pytest
- Git
- PowerShell
- Visual Studio Code
- AI assistant (ChatGPT) for implementation guidance, test design, debugging, and explanation

I reviewed and tested the implementation rather than relying only on generated code. The final test suite passes all implemented tests.

---

## 5. Reasoning Questions

### 1. In Task 6, why must JWT claims not be trusted before signature verification?

JWT claims come from the token and can be modified by an attacker. Signature verification establishes that the claims were issued by a trusted signer and have not been tampered with.

Without verification, an attacker could modify security-sensitive claims such as the user, organization, role, or token purpose and potentially gain unauthorized access.

### 2. In Task 7, why is an offline grace period necessary?

The application may need to continue operating temporarily when the client cannot contact the authorization service. The offline grace period provides controlled continuity without allowing an offline session to remain valid indefinitely.

Once the grace period expires, the client must reconnect so that the session can be checked again.

### 3. In Task 8, why must seat operations be idempotent?

Operations such as invitation, activation, and deactivation may be retried because of network failures, duplicate requests, or repeated user actions.

Without idempotency, the same operation could consume multiple seats or release more seats than were actually allocated. Idempotency ensures repeated operations leave the organization in the same valid state.

### 4. In Task 9, why should authentication errors not expose provider-specific details?

Detailed authentication errors can reveal information about the authentication system or whether a particular account exists. They can also expose internal exception names or implementation details.

Mapping provider errors to controlled application-level responses gives the user useful guidance while reducing information leakage.

### 5. In Task 10, why must authorization checks happen in a specific order?

Authorization depends on trusted information. The token must first be verified before its claims can be trusted. Those claims are then used to evaluate the license and finally determine which requested modules can be granted.

Allowing later authorization decisions to run on unverified or invalid data could create a security bypass.

### 6. In Task 11, why use SHA-256 and numeric version comparison?

SHA-256 provides a deterministic digest that can be compared with a trusted installer digest to detect file modification or corruption.

Version numbers must be compared by their numeric components rather than as strings. For example, string comparison can incorrectly treat `0.1.10` as lower than `0.1.9`, while numeric component comparison produces the correct ordering.



# RBAC Backend — Day 3 Notes

## Submission Completeness / Known Gaps

I am not claiming that all acceptance criteria across Tasks 6–15 are complete.

I reviewed the implementation and understand that passing tests alone do not
prove that every acceptance criterion in the task specification has been met.

For any requirement that I cannot point to in the implementation and verify
through a relevant test or other evidence, I am treating it as unverified or
incomplete rather than claiming it is complete.

In particular:

- Tasks 6–11 have not been marked as fully complete merely because their
  existing tests pass.
- Any acceptance criterion that is not reachable through the public function
  or API signature that was shipped is considered an interface/specification
  gap, not silently treated as complete.
- I am reporting known limitations instead of using a blanket statement that
  nothing remains incomplete.
- Task 15 was optional and was completed, with its rollback limitation
  documented below.
- Task 16 is completed through `SELF_REVIEW.md`.

---

# Task Time Log

The times below are approximate working times, including implementation,
debugging, testing, and review. They are estimates rather than stopwatch-level
measurements.

| Task | Description | Time Consumed |
|---|---|---:|
| Task 12 | JWKS cache, TTL, key rotation and unknown-kid rate limiting | ~1 hr 15 min |
| Task 13 | Seat store, optimistic concurrency and idempotency | ~1 hr 45 min |
| Task 14 | Token claims and licence-based entitlement calculation | ~1 hr |
| Task 15 | Offline licence cache (optional) | ~30 min |
| Task 16 | Self-review and documentation | ~30 min |
| **Total** | | **~5 hrs** |


---

# Task 13 Questions

## 1. Why isn't idempotency alone enough to prevent overselling seats?

Idempotency and optimistic concurrency solve different problems.

Idempotency prevents the same logical request from being applied more than once.
It does not prevent two different requests from both reading the same old
state.

For example, suppose an organisation has 10 seats and 9 are already used.

1. Request A reads version 7 and sees 9 seats used.
2. Request B also reads version 7 and sees 9 seats used.
3. A commits an invite using expected_version=7. It succeeds and changes the
   state to version 8 with 10 seats used.
4. B is a different request with a different request ID and still has
   expected_version=7.
5. Without the optimistic version check, B could also commit using the stale
   state and the count could become 11.

Idempotency cannot prevent this because A and B have different request IDs.

The version check prevents the corruption: B's expected version is 7 but the
current version is 8, so B receives `version_conflict` and does not change the
state.

---

## 2. When would returning version_conflict instead of duplicate_request cause real damage?

Consider a request that succeeds but whose response is lost.

1. The client sends request ID `r1` with expected_version=7.
2. The operation succeeds and the store changes to version 8.
3. The response is lost because of a network failure.
4. The client retries the exact same request ID `r1`, still using expected
   version 7.
5. If the store checks the version before checking completed request IDs, it
   returns `version_conflict`.
6. The client may interpret that as meaning the operation did not complete,
   re-read the state, and submit another operation.

That can cause duplicate side effects.

The correct result for an already completed request is `duplicate_request`,
returning the original committed result without applying the operation again.

`version_conflict` means a new request has an outdated expected version.

`duplicate_request` means that exact logical request has already completed.

The current implementation checks the completed request table before checking
the version, so these cases remain distinct.

---

# Task 12 Questions

## 3. When the fetch fails and the cache is stale, do you serve stale or fail closed?

I chose to fail closed.

When the JWKS cache is stale and the fetch fails, the implementation returns:

`CacheResult(jwks=None, source="unavailable", reason="fetch_failed")`

It does not continue trusting the stale JWKS.

I chose this because authentication should not continue trusting expired key
material indefinitely when the current key set cannot be retrieved.

I would reconsider this if the product requirement placed a stronger priority on
availability during an identity-provider outage. Even then, I would prefer a
strict maximum stale period rather than allowing stale key material
indefinitely.

---

## 4. What does an attacker still get to do with unknown-kid requests, and why is that acceptable?

An attacker can still send many tokens containing arbitrary unknown `kid`
values.

Those requests still reach the token-verification path and the application
must inspect them. After the configured minimum interval has passed, an
unknown-kid request can trigger another JWKS fetch.

However, the attacker cannot cause an outbound JWKS fetch for every unknown
`kid`. The implementation records the last unknown-kid refresh attempt and
returns `unknown_kid_refetch_rate_limited` while the five-minute interval has
not elapsed.

This is acceptable because an unknown `kid` can also represent legitimate key
rotation. The rate limit preserves the ability to discover a newly rotated key
while preventing an attacker from turning every token verification into an
outbound fetch.

---

# Task 14 Question

## 5. Why does the Pre-Token Lambda compute entitlements at sign-in instead of reading a stored list?

The token claims builder computes module entitlements from the current licence
and the user's requested modules at token issuance time.

It evaluates the current licence using the supplied `now` value and calls
`resolve_user_modules()` only when the licence is valid.

This means the token reflects the licence state at the time it is issued. If a
licence is revoked at 2pm on a Tuesday, a token issued after 2pm will not
receive the revoked modules; the `modules` claim becomes empty because the
licence is invalid.

Computing entitlements at token issuance therefore prevents a previously
stored entitlement list from continuing to grant modules after the licence
has been revoked or otherwise become invalid.

---

# Day 2 Re-answers

## RS256 / HS256 confusion attack

The attack is possible when a verifier accepts both RS256 and HS256 and
incorrectly uses an RSA public key as the HMAC secret.

The RSA public key is public, so an attacker could obtain it and create an
HS256 token using that public key as the HMAC secret. If the verifier accepts
that token, the attacker could potentially forge authentication claims.

The defence is algorithm pinning: the verifier accepts only RS256 and verifies
the signature using the trusted RSA public key.

---

## User enumeration through different login errors

An authentication endpoint can reveal whether an account exists if it gives
different responses for an unknown email and a known email with an incorrect
password.

For example:

1. The attacker submits `alice@example.com` with a wrong password.
2. The attacker submits `doesnotexist@example.com` with a wrong password.
3. If the responses differ, the attacker learns that Alice's account exists.
4. Repeating this over a large list can enumerate valid accounts.

The defence is to return the same externally visible authentication failure for
both cases, rather than revealing whether the account exists.

---

## SENSITIVE_KEYS

Sensitive fields should be identified using the intended key names rather than
broad substring matching.

Broad substring matching can create false positives. For example, an unrelated
field whose name merely contains a sensitive-looking word could be treated as
secret data even when it is not.

An explicit set of sensitive keys makes sanitization predictable and avoids
accidentally treating unrelated fields as secrets.

---

# Task 15 — Optional Offline Licence Cache

Task 15 was optional, but it was completed.

The offline cache uses HMAC-SHA256 to protect the sealed licence payload, and
signature comparison uses constant-time comparison so edits to the sealed
cache can be detected.

The cache also uses time information to reject clearly invalid cache data.

However, local HMAC cannot completely prevent rollback on a machine whose owner
can modify local files.

A user can save an older, genuinely signed cache and restore it after the
licence has expired. The signature remains valid because the older cache really
was issued and signed by the trusted issuer.

Therefore Task 15 detects tampering with the signed contents but does not prove
that a valid cache is the newest cache.

Complete rollback prevention would require trusted external state or another
trusted monotonic mechanism outside ordinary user-editable local storage.

This limitation is intentional and follows the task specification's warning
that local rollback cannot be completely solved when the machine owner can
edit local files.

---

## Tools Used Today

- ChatGPT — AI coding and review assistance
- VS Code — Code editing
- PowerShell — Development terminal
- Python — Runtime checks and validation
- Pytest — Automated testing
- Git — Version control
- GitHub — Remote repository and submission

# Task 16 — Self-review

The detailed self-review is documented separately in `SELF_REVIEW.md`.

The self-review identifies concrete defects rather than style issues.

The defects identified include:

1. Non-canonical persisted member email keys can cause duplicate logical users
   to consume multiple seats.
2. Non-finite `exp` values such as infinity can cause JWT verification to raise
   `OverflowError` instead of returning `malformed`.
3. Non-finite `nbf` values can cause the same type of failure.

These are treated as actual correctness defects because they produce incorrect
behaviour for concrete inputs rather than merely being style concerns.

The self-review records the location, concrete failure, impact, and whether each
defect is fixed.

---

# Review Discipline

I will not use a blanket statement such as "nothing remains incomplete" unless
I have checked the individual acceptance criteria.

For every future task, I will review the specification itself and ask:

1. Where in the code is this requirement implemented?
2. Which test demonstrates it?
3. Can the requirement actually be reached through the public function/API
   signature?
4. What happens for invalid, repeated, concurrent, and boundary inputs?
5. Are there any assumptions that do not hold?
6. If a requirement is not implemented, not testable, or impossible through the
   shipped interface, have I explicitly reported it?

Passing tests are evidence for the behaviour they cover. They are not by
themselves evidence that every acceptance criterion is complete.

If I find an incomplete or unverified requirement, I will report it explicitly
instead of silently treating the task as complete.
