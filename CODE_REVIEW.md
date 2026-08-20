# Task 25 — Code Review

## Review target

`day4_review_target.py`

## Review scope

Reviewed as a proposed merge into `backend/src/rbac/`.

The review focuses on authorization correctness, security, failure handling, state management, caching, secret handling, and seat allocation.

## Severity scale

* **Critical** — Can directly grant unauthorized access, expose credentials, or cause a severe security/correctness failure.
* **High** — Can cause unauthorized access, incorrect entitlement/seat state, or significant security risk under realistic conditions.
* **Medium** — Causes incorrect behavior or creates a meaningful reliability/security issue, but does not directly grant unauthorized access in the normal case.
* **Low** — Limited impact or primarily maintainability/robustness concern.

---

## Defect 1 — Authorization fails open on unexpected errors

**Where:** `EntitlementService.authorize()`, lines 197–200.

**Severity:** Critical

**What breaks:**

The exception handler returns:

```python
AuthResult(True, requested, "degraded")
```

for any exception raised during authorization.

For example, if token verification fails or the requested organization does not exist, authorization can enter the exception handler and return:

```python
allowed=True
modules=requested
```

instead of denying access.

**Why it happens:**

The error-handling policy is fail-open. The service treats an inability to establish authorization as permission to continue.

**The fix:**

Authorization errors should fail closed. Return a denied result with no granted modules, for example:

```python
return AuthResult(False, [], "Authorization failed.")
```

Unexpected exceptions should not grant the requested modules.

---

## Defect 2 — Full JWT is written to the logs

**Where:** `EntitlementService.verify()`, line 87.

**Severity:** Critical

**What breaks:**

The complete supplied JWT is included in the log message:

```python
logger.info("verifying token %s for issuer %s", token, self.issuer)
```

Anyone with access to application logs may obtain the bearer token.

**Why it happens:**

The implementation logs the authentication credential itself rather than a non-sensitive identifier or operational status.

**The fix:**

Never log the token. Log only non-sensitive information, for example:

```python
logger.info("verifying token for issuer %s", self.issuer)
```

---

## Defect 3 — Entitlement cache ignores the requested modules

**Where:** `EntitlementService.entitlements_for()`, lines 138–152.

**Severity:** High

**What breaks:**

The cache is keyed only by `org_id`:

```python
cached = self.cache.get(org_id)
```

The `requested` modules are not part of the cache key.

For example, if the first request is:

```python
entitlements_for("org-1", ["fcs", "nta"])
```

and the result is cached, a later request:

```python
entitlements_for("org-1", ["fcs"])
```

can return the previously cached result containing both modules.

The returned entitlement set therefore does not necessarily correspond to the current request.

**Why it happens:**

The cache key does not contain all inputs that influence the function's result.

**The fix:**

Either cache the organization's complete entitlement state and intersect it with `requested` for every call, or include a normalized representation of `requested` in the cache key.

---

## Defect 4 — Entitlement cache does not expire

**Where:** `EntitlementService.entitlements_for()`, lines 138–152, together with `ENTITLEMENT_CACHE_TTL` at line 23.

**Severity:** High

**What breaks:**

The module defines:

```python
ENTITLEMENT_CACHE_TTL = timedelta(hours=6)
```

but the cache never records an insertion time and never checks the TTL.

Once an entitlement result is cached, it can remain in the cache indefinitely.

For example, an organization may initially have `fcs`, causing `fcs` to be cached. If `fcs` is later removed from the organization's modules, the cached result can continue to grant it.

**Why it happens:**

The declared cache lifetime is not implemented in the cache lookup/update logic.

**The fix:**

Store the cached value together with its creation time and recompute it after the configured TTL. Entitlement or license changes should also invalidate affected cached entries where appropriate.

---

## Defect 5 — Mutable default argument shares the entitlement cache

**Where:** `EntitlementService.__init__()`, line 49.

**Severity:** High

**What breaks:**

The constructor uses:

```python
cache={}
```

as a default argument.

Python creates this dictionary once and reuses it across calls that omit the argument.

Therefore, multiple `EntitlementService` instances can unintentionally share the same cache.

**Why it happens:**

Mutable objects used as Python default arguments are created once at function definition time rather than once per invocation.

**The fix:**

Use `None` as the default and create a new dictionary when needed:

```python
def __init__(self, jwks, issuer, audience, orgs=None, cache=None):
    self.cache = {} if cache is None else cache
```

---

## Defect 6 — Seat limit check allows an extra seat

**Where:** `EntitlementService.invite_member()`, lines 121–129.

**Severity:** High

**What breaks:**

The implementation checks:

```python
if current > org.seats_total:
    return False
```

If:

```text
seats_total = 5
seats_used = 5
```

the condition is false, so another invitation is allowed and `seats_used` becomes 6.

The organization can therefore exceed its licensed seat count.

**Why it happens:**

The boundary condition is incorrect. Allocation must be rejected when all licensed seats are already used.

**The fix:**

Use:

```python
if current >= org.seats_total:
    return False
```

The check and the subsequent update should also be made atomic.

---

## Defect 7 — Seat allocation has a check-then-act race

**Where:** `EntitlementService.invite_member()`, lines 121–130.

**Severity:** High

**What breaks:**

The current seat count is read and checked before the state is updated:

```python
current = org.seats_used

if current > org.seats_total:
    return False

time.sleep(0)

org.members[email] = "pending"
org.seats_used = current + 1
```

Two concurrent invitations can both read the same `current` value and both pass the capacity check.

For example, with:

```text
seats_total = 5
seats_used = 4
```

two concurrent requests can both observe 4 and both proceed.

The organization can therefore create more pending members than available seats even though the counter may only reflect one increment.

**Why it happens:**

The capacity check and seat increment are separate operations. Another request can modify the state between the read and write.

**The fix:**

Perform the capacity check and seat reservation atomically using the persistence layer's transaction/locking mechanism.

---

## Defect 8 — Duplicate invitations consume additional seats

**Where:** `EntitlementService.invite_member()`, lines 117–130.

**Severity:** Medium

**What breaks:**

The method does not check whether `email` already exists in `org.members`.

Calling:

```python
invite_member("org-1", "bob@example.com")
```

twice overwrites the same member entry but increments `seats_used` twice.

A single member can therefore consume multiple seats.

**Why it happens:**

The method treats every invitation request as a new reservation without checking for an existing member or pending invitation.

**The fix:**

Check for an existing normalized member/invitation before reserving another seat. The operation should be idempotent for an already-pending member.

---

## Defect 9 — Activation token comparison is not constant-time

**Where:** `EntitlementService.redeem_activation()`, line 108.

**Severity:** Medium

**What breaks:**

The secret values are compared using normal equality:

```python
if provided_token == stored_token:
```

This is not the appropriate comparison primitive for secret values.

**Why it happens:**

The implementation uses normal string comparison rather than a constant-time comparison intended for secrets.

**The fix:**

Use `hmac.compare_digest()`:

```python
import hmac

if hmac.compare_digest(provided_token, stored_token):
    return True
```

---

## Defect 10 — Activation tokens with future issue times are accepted

**Where:** `EntitlementService.redeem_activation()`, lines 103–106.

**Severity:** Medium

**What breaks:**

The expiry calculation only checks whether the token is older than the TTL:

```python
if datetime.now(timezone.utc) - issued_at > ACTIVATION_TOKEN_TTL:
    return False
```

It does not reject an `issued_at` value in the future.

For example, if the current time is 10:00 UTC and `issued_at` is 12:00 UTC, the calculated age is negative and the token passes the expiry check.

**Why it happens:**

The implementation validates maximum age but does not validate that the issuance time is reasonable and not in the future.

**The fix:**

Reject future issue times beyond an explicitly documented clock-skew allowance before applying the TTL check.

---

## Defect 11 — Login errors reveal whether an account exists

**Where:** `EntitlementService.login_error()`, lines 160–171.

**Severity:** Medium

**What breaks:**

The method returns different messages for different authentication failures.

For example:

```python
login_error("UserNotFoundException")
```

returns:

```text
No account exists for that email address.
```

while:

```python
login_error("NotAuthorizedException")
```

returns:

```text
Incorrect password. Please try again.
```

An unauthenticated caller can therefore distinguish an email address that does not have an account from one that does.

**Why it happens:**

The implementation exposes the provider's internal authentication failure type directly through different user-facing responses.

**The fix:**

Return the same generic authentication failure message for account-not-found and incorrect-password cases, for example:

```text
Sign-in failed. Please check your credentials and try again.
```

The application can still log the internal exception type for operational purposes without exposing the distinction to the caller.

---

# Interaction between defects

The two entitlement-cache defects interact and make the cache result unreliable in two different ways.

First, the cache is keyed only by `org_id`, so it does not account for the `requested` modules. A result calculated for one request can therefore be returned for a different request.

Second, the cache does not actually enforce the declared six-hour TTL, so an old result can remain cached indefinitely.

For example, a request for:

```python
entitlements_for("org-1", ["fcs", "nta"])
```

can cache:

```text
["fcs", "nta"]
```

A later request for:

```python
entitlements_for("org-1", ["fcs"])
```

can receive the previous cached result because the cache key contains only `org-1`.

If the organization's module entitlements then change, the same cached result can continue to be returned because the cache has no effective expiration.

The user experience is therefore that the launcher can receive an entitlement list that is both unrelated to the current requested set and older than the underlying organization state.

These defects should be fixed together: the cache must represent all inputs that affect the result and must have a real expiration/invalidation policy.

---

# Merge decision

## Do not merge

I would not merge this implementation in its current form.

Before merging, I would require at minimum:

1. Authorization to fail closed on all verification/resolution errors.
2. Removal of JWTs and other credentials from logs.
3. Correct entitlement cache keying and expiration/invalidation.
4. Correct seat-boundary handling.
5. Atomic seat allocation.
6. Idempotent handling of duplicate invitations.
7. Constant-time activation-token comparison.
8. Tests covering the above security and state-management cases.

The critical authorization and credential-handling defects should be fixed before any deployment.

---

# If only three defects could be fixed

## 1. Authorization fails open

This is the highest-priority defect because it can directly turn an authorization failure into successful access.

## 2. JWT is logged

A leaked bearer token can be used as an authentication credential, making credential exposure a direct security risk.

## 3. Stale/incorrect entitlement caching

Authorization decisions must reflect current entitlement state. The current cache can return results that no longer match the organization's modules and can also ignore the caller's requested module set.

I would prioritize these three because they most directly affect whether an unauthorized user can obtain access or credentials.

---

# Final review conclusion

**Do not merge.**

The implementation has multiple correctness and security defects. The most serious are the fail-open authorization path, credential logging, and incorrect entitlement caching. Seat allocation also requires transactional protection because the current check/update sequence is not safe under concurrent requests.

The defects should be fixed and covered by regression tests before the service is considered merge-ready.
