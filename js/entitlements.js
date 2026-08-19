'use strict';

/*
 * Task 23 - JavaScript entitlement / launcher layer.
 *
 * Security model:
 * - Fail closed on malformed claims.
 * - Never grant an unknown SKU.
 * - Never infer entitlements from missing data.
 * - Licence validity is evaluated at the time of the call.
 * - "Locked" is different from "hidden": known tiles remain visible.
 * - `now` is injected so the behaviour is deterministic and testable.
 */

const BASE_MODULES = Object.freeze([
  'fcs',
  'nta',
  'tem',
  'western',
]);

const ADDON_MODULES = Object.freeze([
  'cross_compare',
  'ai_chat',
]);

const ALL_MODULES = Object.freeze([
  ...BASE_MODULES,
  ...ADDON_MODULES,
]);

const BASE_MODULE_SET = new Set(BASE_MODULES);
const ALL_MODULE_SET = new Set(ALL_MODULES);

const ACTIVE_LICENSE_STATUSES = new Set([
  'active',
  'perpetual',
]);

const INVALID_LICENSE_STATUSES = new Set([
  'expired',
  'revoked',
  'suspended',
  'invalid',
]);

const TILE_REASONS = Object.freeze({
  LICENSED: 'licensed',
  NOT_LICENSED: 'not_licensed',
  REQUIRES_TWO_BASE_MODULES: 'requires_two_base_modules',
  LICENSE_EXPIRED: 'license_expired',
  LICENSE_REVOKED: 'license_revoked',
  LICENSE_SUSPENDED: 'license_suspended',
  LICENSE_INVALID: 'license_invalid',
  LICENSE_UNUSABLE: 'license_unusable',
  INVALID_CLAIMS: 'invalid_claims',
});

/**
 * Determine whether a value is a plain object.
 *
 * Arrays, null, Dates, and class instances are deliberately rejected.
 */
function isPlainObject(value) {
  if (value === null || typeof value !== 'object') {
    return false;
  }

  const prototype = Object.getPrototypeOf(value);

  return prototype === Object.prototype || prototype === null;
}

/**
 * Normalize a module claim into a Set.
 *
 * Accepted:
 *   "fcs,nta"
 *   ["fcs", "nta"]
 *   [" FCS ", "nta"]
 *
 * Rejected:
 *   null
 *   undefined
 *   numbers
 *   objects
 *   arrays containing non-strings
 *   blank entries
 *
 * Returning null instead of an empty Set is important:
 * an invalid claim must not be confused with a valid empty entitlement.
 */
function normalizeModules(modules) {
  if (typeof modules === 'string') {
    const value = modules.trim();

    if (value === '') {
      return new Set();
    }

    const parts = value.split(',');

    const normalized = new Set();

    for (const part of parts) {
      if (typeof part !== 'string') {
        return null;
      }

      const sku = part.trim().toLowerCase();

      if (sku === '') {
        /*
         * Example:
         *   "fcs,,nta"
         *
         * Do not silently repair malformed claims.
         */
        return null;
      }

      normalized.add(sku);
    }

    return normalized;
  }

  if (Array.isArray(modules)) {
    const normalized = new Set();

    for (const item of modules) {
      if (typeof item !== 'string') {
        return null;
      }

      const sku = item.trim().toLowerCase();

      if (sku === '') {
        return null;
      }

      normalized.add(sku);
    }

    return normalized;
  }

  return null;
}

/**
 * Validate the injected clock.
 */
function normalizeNow(now) {
  if (!(now instanceof Date)) {
    return null;
  }

  if (Number.isNaN(now.getTime())) {
    return null;
  }

  return now;
}

/**
 * Parse an expiry claim safely.
 *
 * The claim must be a non-empty string and represent a valid date.
 */
function parseExpiry(expires) {
  if (typeof expires !== 'string') {
    return null;
  }

  const value = expires.trim();

  if (value === '') {
    return null;
  }

  const timestamp = Date.parse(value);

  if (Number.isNaN(timestamp)) {
    return null;
  }

  return timestamp;
}

/**
 * Normalize a licence status.
 */
function normalizeLicenseStatus(status) {
  if (typeof status !== 'string') {
    return null;
  }

  const normalized = status.trim().toLowerCase();

  if (normalized === '') {
    return null;
  }

  return normalized;
}

/**
 * Determine whether the licence is currently usable.
 *
 * Returns an object instead of a boolean so callers can preserve
 * the precise reason for a locked tile.
 */
function evaluateLicense(claims, now) {
  if (!isPlainObject(claims)) {
    return {
      usable: false,
      reason: TILE_REASONS.INVALID_CLAIMS,
    };
  }

  const normalizedNow = normalizeNow(now);

  if (normalizedNow === null) {
    return {
      usable: false,
      reason: TILE_REASONS.INVALID_CLAIMS,
    };
  }

  const status = normalizeLicenseStatus(claims.license_status);

  if (status === null) {
    return {
      usable: false,
      reason: TILE_REASONS.LICENSE_UNUSABLE,
    };
  }

  if (status === 'expired') {
    return {
      usable: false,
      reason: TILE_REASONS.LICENSE_EXPIRED,
    };
  }

  if (status === 'revoked') {
    return {
      usable: false,
      reason: TILE_REASONS.LICENSE_REVOKED,
    };
  }

  if (status === 'suspended') {
    return {
      usable: false,
      reason: TILE_REASONS.LICENSE_SUSPENDED,
    };
  }

  if (status === 'invalid') {
    return {
      usable: false,
      reason: TILE_REASONS.LICENSE_INVALID,
    };
  }

  if (!ACTIVE_LICENSE_STATUSES.has(status)) {
    return {
      usable: false,
      reason: TILE_REASONS.LICENSE_UNUSABLE,
    };
  }

  /*
   * Perpetual licences intentionally have no expiry requirement.
   */
  if (status === 'perpetual') {
    return {
      usable: true,
      reason: TILE_REASONS.LICENSED,
    };
  }

  /*
   * Active licences require a valid expiry.
   */
  if (!Object.prototype.hasOwnProperty.call(claims, 'license_expires')) {
    return {
      usable: false,
      reason: TILE_REASONS.LICENSE_UNUSABLE,
    };
  }

  const expiryTimestamp = parseExpiry(claims.license_expires);

  if (expiryTimestamp === null) {
    return {
      usable: false,
      reason: TILE_REASONS.LICENSE_UNUSABLE,
    };
  }

  /*
   * At the exact expiry instant, the licence is expired.
   */
  if (normalizedNow.getTime() >= expiryTimestamp) {
    return {
      usable: false,
      reason: TILE_REASONS.LICENSE_EXPIRED,
    };
  }

  return {
    usable: true,
    reason: TILE_REASONS.LICENSED,
  };
}

/**
 * Return only known base modules from a normalized module set.
 *
 * Unknown SKUs are ignored rather than becoming grants.
 */
function getLicensedBaseModules(modules) {
  const baseModules = new Set();

  for (const sku of modules) {
    if (BASE_MODULE_SET.has(sku)) {
      baseModules.add(sku);
    }
  }

  return baseModules;
}

/**
 * Check whether a single SKU is licensed.
 */
function isLicensed(claims, sku, now) {
  if (!isPlainObject(claims)) {
    return false;
  }

  if (typeof sku !== 'string') {
    return false;
  }

  const normalizedSku = sku.trim().toLowerCase();

  /*
   * Never grant arbitrary/unknown module names.
   */
  if (!ALL_MODULE_SET.has(normalizedSku)) {
    return false;
  }

  const license = evaluateLicense(claims, now);

  if (!license.usable) {
    return false;
  }

  const modules = normalizeModules(claims.modules);

  if (modules === null) {
    return false;
  }

  /*
   * Base module:
   * it must explicitly exist in the claim.
   */
  if (BASE_MODULE_SET.has(normalizedSku)) {
    return modules.has(normalizedSku);
  }

  /*
   * cross_compare:
   * explicit entitlement PLUS at least two licensed base modules.
   */
  if (normalizedSku === 'cross_compare') {
    if (!modules.has('cross_compare')) {
      return false;
    }

    const licensedBaseModules = getLicensedBaseModules(modules);

    return licensedBaseModules.size >= 2;
  }

  /*
   * ai_chat:
   * explicit entitlement only.
   */
  if (normalizedSku === 'ai_chat') {
    return modules.has('ai_chat');
  }

  /*
   * Defensive fallback.
   *
   * This should be unreachable because ALL_MODULE_SET is authoritative.
   */
  return false;
}

/**
 * Return the reason why a known SKU is locked.
 */
function getModuleLockReason(modules, sku) {
  if (sku === 'cross_compare' && modules.has('cross_compare')) {
    const baseModules = getLicensedBaseModules(modules);

    if (baseModules.size < 2) {
      return TILE_REASONS.REQUIRES_TWO_BASE_MODULES;
    }
  }

  return TILE_REASONS.NOT_LICENSED;
}

/**
 * Build launcher tile states.
 *
 * Important:
 * - Every known SKU is returned.
 * - Unlicensed/expired modules are LOCKED, not hidden.
 * - Unknown SKUs never appear.
 * - Malformed claims never throw.
 */
function tileStates(claims, now) {
  const normalizedNow = normalizeNow(now);

  if (!isPlainObject(claims) || normalizedNow === null) {
    return ALL_MODULES.map((sku) => ({
      sku,
      licensed: false,
      locked: true,
      reason: TILE_REASONS.INVALID_CLAIMS,
    }));
  }

  const license = evaluateLicense(claims, normalizedNow);

  /*
   * Invalid module structure is different from a legitimate empty
   * entitlement list. Both fail closed, but the former is explicitly
   * marked invalid.
   */
  const modules = normalizeModules(claims.modules);

  if (modules === null) {
    return ALL_MODULES.map((sku) => ({
      sku,
      licensed: false,
      locked: true,
      reason: TILE_REASONS.INVALID_CLAIMS,
    }));
  }

  /*
   * Licence-level failure locks every known tile.
   */
  if (!license.usable) {
    return ALL_MODULES.map((sku) => ({
      sku,
      licensed: false,
      locked: true,
      reason: license.reason,
    }));
  }

  return ALL_MODULES.map((sku) => {
    const licensed = isLicensed(
      claims,
      sku,
      normalizedNow,
    );

    return {
      sku,
      licensed,
      locked: !licensed,
      reason: licensed
        ? TILE_REASONS.LICENSED
        : getModuleLockReason(modules, sku),
    };
  });
}

module.exports = {
  BASE_MODULES,
  ADDON_MODULES,
  ALL_MODULES,
  normalizeModules,
  evaluateLicense,
  isLicensed,
  tileStates,
};