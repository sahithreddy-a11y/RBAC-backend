'use strict';

/*
 * Task 27 — Locked-tile view model
 *
 * Pure function:
 *   - no DOM
 *   - no Electron
 *   - no network
 *   - current time is injected
 *
 * Task 23 defines the entitlement model.
 */

const MODULES = Object.freeze([
    Object.freeze({
        sku: 'fcs',
        label: 'FCS',
    }),
    Object.freeze({
        sku: 'nta',
        label: 'NTA',
    }),
    Object.freeze({
        sku: 'tem',
        label: 'TEM',
    }),
    Object.freeze({
        sku: 'western',
        label: 'Western Blot',
    }),
    Object.freeze({
        sku: 'cross_compare',
        label: 'Cross-Compare',
    }),
    Object.freeze({
        sku: 'ai_chat',
        label: 'AI Chat',
    }),
]);

const BASE_MODULES = new Set([
    'fcs',
    'nta',
    'tem',
    'western',
]);

const VALID_ACTIONS = new Set([
    'launch',
    'install',
    'contact_sales',
    'none',
]);


/**
 * Normalize the Task 23 modules claim.
 *
 * Task 23 supports:
 *   "fcs,nta"
 *   ["fcs", "nta"]
 *
 * Malformed values fail closed.
 */
function normalizeModules(claims) {
    if (
        claims === null ||
        typeof claims !== 'object' ||
        Array.isArray(claims)
    ) {
        return null;
    }

    const value = claims.modules;

    if (typeof value === 'string') {
        return value
            .split(',')
            .map((module) => module.trim())
            .filter((module) => module.length > 0);
    }

    if (Array.isArray(value)) {
        const result = [];

        for (const module of value) {
            if (typeof module !== 'string') {
                return null;
            }

            const normalized = module.trim();

            if (normalized.length > 0) {
                result.push(normalized);
            }
        }

        return result;
    }

    return null;
}


/**
 * Determine licence state.
 *
 * Task 27 requires expired licences to have a different reason
 * from never-licensed modules.
 *
 * Invalid expiry data fails closed.
 */
function getLicenseState(claims, now) {
    if (
        claims === null ||
        typeof claims !== 'object' ||
        Array.isArray(claims)
    ) {
        return {
            valid: false,
            expired: false,
            malformed: true,
        };
    }

    if (!(now instanceof Date) || Number.isNaN(now.getTime())) {
        return {
            valid: false,
            expired: false,
            malformed: true,
        };
    }

    const status = claims.license_status;

    /*
     * If Task 23 provided a status, it must be a string.
     * An explicit non-active status is not treated as active.
     */
    if (
        status !== undefined &&
        status !== null &&
        typeof status !== 'string'
    ) {
        return {
            valid: false,
            expired: false,
            malformed: true,
        };
    }

    if (
        typeof status === 'string' &&
        status.trim() !== '' &&
        status !== 'active'
    ) {
        return {
            valid: false,
            expired: false,
            malformed: false,
        };
    }

    const expiry = claims.license_expires;

    /*
     * No expiry / perpetual means the licence does not expire.
     */
    if (
        expiry === undefined ||
        expiry === null ||
        expiry === '' ||
        expiry === 'perpetual'
    ) {
        return {
            valid: true,
            expired: false,
            malformed: false,
        };
    }

    if (typeof expiry !== 'string') {
        return {
            valid: false,
            expired: false,
            malformed: true,
        };
    }

    const expiryDate = new Date(expiry);

    if (Number.isNaN(expiryDate.getTime())) {
        return {
            valid: false,
            expired: false,
            malformed: true,
        };
    }

    /*
     * Exactly at expiry is expired.
     */
    if (expiryDate.getTime() <= now.getTime()) {
        return {
            valid: false,
            expired: true,
            malformed: false,
        };
    }

    return {
        valid: true,
        expired: false,
        malformed: false,
    };
}


/**
 * Create a locked tile.
 */
function createLockedTile(
    module,
    badge,
    tooltip,
    action,
) {
    return {
        sku: module.sku,
        label: module.label,
        licensed: false,
        locked: true,
        badge,
        tooltip,
        action,
    };
}


/**
 * Create a licensed tile.
 *
 * The only difference between installed and not-installed
 * licensed tiles is the action.
 */
function createLicensedTile(module, installed) {
    return {
        sku: module.sku,
        label: module.label,
        licensed: true,
        locked: false,
        badge: null,
        tooltip: '',
        action: installed ? 'launch' : 'install',
    };
}


/**
 * Build the six launcher tiles.
 *
 * @param {object} claims
 * @param {Date} now
 * @param {string[]} installedSkus
 *
 * @returns {{
 *   sku: string,
 *   label: string,
 *   licensed: boolean,
 *   locked: boolean,
 *   badge: string|null,
 *   tooltip: string,
 *   action: 'launch'|'install'|'contact_sales'|'none'
 * }[]}
 */
function tileViewModel(claims, now, installedSkus) {
    /*
     * installedSkus is machine state, not entitlement state.
     * Invalid machine-state input must not cause a launcher crash.
     */
    if (!Array.isArray(installedSkus)) {
        return MODULES.map((module) =>
            createLockedTile(
                module,
                'Unavailable',
                'Module unavailable because entitlement information is invalid.',
                'none',
            ),
        );
    }

    /*
     * Defensive validation of installed SKU entries.
     */
    if (
        installedSkus.some(
            (sku) => typeof sku !== 'string',
        )
    ) {
        return MODULES.map((module) =>
            createLockedTile(
                module,
                'Unavailable',
                'Module unavailable because entitlement information is invalid.',
                'none',
            ),
        );
    }

    const modules = normalizeModules(claims);

    /*
     * Malformed claims:
     * all six tiles remain visible,
     * all are locked,
     * action is none,
     * nothing throws.
     */
    if (modules === null) {
        return MODULES.map((module) =>
            createLockedTile(
                module,
                'Unavailable',
                'Module unavailable because entitlement information is invalid.',
                'none',
            ),
        );
    }

    const licenseState = getLicenseState(claims, now);

    if (licenseState.malformed) {
        return MODULES.map((module) =>
            createLockedTile(
                module,
                'Unavailable',
                'Module unavailable because entitlement information is invalid.',
                'none',
            ),
        );
    }

    /*
     * Expired is a distinct reason and therefore gets its own tooltip.
     */
    if (licenseState.expired) {
        return MODULES.map((module) =>
            createLockedTile(
                module,
                'Expired',
                'Your licence has expired.',
                'contact_sales',
            ),
        );
    }

    /*
     * A validly shaped but inactive/revoked licence is not licensed.
     */
    if (!licenseState.valid) {
        return MODULES.map((module) =>
            createLockedTile(
                module,
                'Not licensed',
                'This module is not licensed.',
                'contact_sales',
            ),
        );
    }

    const licensedSkus = new Set(
        modules.filter((sku) =>
            BASE_MODULES.has(sku) ||
            sku === 'ai_chat' ||
            sku === 'cross_compare',
        ),
    );

    /*
     * Task 23:
     *
     * cross_compare requires ownership of the SKU AND
     * at least two base modules.
     */
    const baseModuleCount = modules.filter(
        (sku) => BASE_MODULES.has(sku),
    ).length;

    const crossCompareOwned =
        licensedSkus.has('cross_compare');

    const crossCompareHasEnoughBases =
        baseModuleCount >= 2;

    const installed = new Set(installedSkus);

    return MODULES.map((module) => {
        const { sku } = module;

        /*
         * cross_compare has two distinct locked reasons:
         *
         * 1. Not owned.
         * 2. Owned but fewer than two base modules.
         */
        if (sku === 'cross_compare') {
            if (!crossCompareOwned) {
                return createLockedTile(
                    module,
                    'Not licensed',
                    'This module is not licensed.',
                    'contact_sales',
                );
            }

            if (!crossCompareHasEnoughBases) {
                return createLockedTile(
                    module,
                    'Requires 2 modules',
                    'Cross-Compare requires at least two base modules.',
                    'none',
                );
            }

            return createLicensedTile(
                module,
                installed.has(sku),
            );
        }

        /*
         * Ordinary licensed module.
         */
        if (licensedSkus.has(sku)) {
            return createLicensedTile(
                module,
                installed.has(sku),
            );
        }

        /*
         * Not licensed:
         * tile stays visible and greyed.
         */
        return createLockedTile(
            module,
            'Not licensed',
            'This module is not licensed.',
            'contact_sales',
        );
    });
}


module.exports = {
    MODULES,
    BASE_MODULES,
    normalizeModules,
    getLicenseState,
    tileViewModel,
};