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

No known required functionality from Tasks 1–5 remains incomplete.

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

No known required functionality from Tasks 6–11 remains incomplete.

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
