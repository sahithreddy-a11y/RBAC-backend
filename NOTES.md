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
