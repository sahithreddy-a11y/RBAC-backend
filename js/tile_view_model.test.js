'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');

const {
    MODULES,
    normalizeModules,
    getLicenseState,
    tileViewModel,
} = require('./tile_view_model');


const NOW = new Date('2026-08-20T10:00:00.000Z');


function makeClaims(
    modules,
    overrides = {},
) {
    return {
        sub: 'user-1',
        org_id: 'org-1',
        role: 'researcher',
        modules,
        license_status: 'active',
        license_expires: '2027-08-20T10:00:00.000Z',
        ...overrides,
    };
}


function tile(result, sku) {
    const found = result.find(
        (item) => item.sku === sku,
    );

    assert.ok(
        found,
        `Expected tile ${sku} to exist`,
    );

    return found;
}


/*
 * --------------------------------------------------------------------------
 * Stable output
 * --------------------------------------------------------------------------
 */


test('returns exactly six SKUs in stable order', () => {
    const result = tileViewModel(
        makeClaims([]),
        NOW,
        [],
    );

    assert.deepEqual(
        result.map((item) => item.sku),
        [
            'fcs',
            'nta',
            'tem',
            'western',
            'cross_compare',
            'ai_chat',
        ],
    );

    assert.equal(result.length, 6);
});


test('stable order is independent of claim order', () => {
    const first = tileViewModel(
        makeClaims('fcs,nta,tem'),
        NOW,
        [],
    );

    const second = tileViewModel(
        makeClaims('tem,nta,fcs'),
        NOW,
        [],
    );

    assert.deepEqual(
        first.map((item) => item.sku),
        second.map((item) => item.sku),
    );
});


/*
 * --------------------------------------------------------------------------
 * Task 23 claim shapes
 * --------------------------------------------------------------------------
 */


test('accepts comma-separated modules', () => {
    assert.deepEqual(
        normalizeModules(
            makeClaims('fcs,nta,ai_chat'),
        ),
        [
            'fcs',
            'nta',
            'ai_chat',
        ],
    );
});


test('accepts array modules', () => {
    assert.deepEqual(
        normalizeModules(
            makeClaims([
                'fcs',
                'nta',
                'ai_chat',
            ]),
        ),
        [
            'fcs',
            'nta',
            'ai_chat',
        ],
    );
});


test('array and string claim forms produce equivalent view models', () => {
    const stringResult = tileViewModel(
        makeClaims('fcs,nta'),
        NOW,
        [],
    );

    const arrayResult = tileViewModel(
        makeClaims(['fcs', 'nta']),
        NOW,
        [],
    );

    assert.deepEqual(
        stringResult,
        arrayResult,
    );
});


test('whitespace in module string is normalized', () => {
    assert.deepEqual(
        normalizeModules(
            makeClaims(' fcs, nta, ai_chat '),
        ),
        [
            'fcs',
            'nta',
            'ai_chat',
        ],
    );
});


test('empty module entries are ignored', () => {
    assert.deepEqual(
        normalizeModules(
            makeClaims('fcs,,nta, ,ai_chat,'),
        ),
        [
            'fcs',
            'nta',
            'ai_chat',
        ],
    );
});


/*
 * --------------------------------------------------------------------------
 * Licensed / installed
 * --------------------------------------------------------------------------
 */


test('licensed and installed means launch', () => {
    const result = tileViewModel(
        makeClaims('fcs'),
        NOW,
        ['fcs'],
    );

    const item = tile(result, 'fcs');

    assert.equal(item.licensed, true);
    assert.equal(item.locked, false);
    assert.equal(item.action, 'launch');
});


test('licensed but not installed means install', () => {
    const result = tileViewModel(
        makeClaims('fcs'),
        NOW,
        [],
    );

    const item = tile(result, 'fcs');

    assert.equal(item.licensed, true);
    assert.equal(item.locked, false);
    assert.equal(item.action, 'install');
});


test('installed state does not grant entitlement', () => {
    const result = tileViewModel(
        makeClaims(''),
        NOW,
        ['fcs'],
    );

    const item = tile(result, 'fcs');

    assert.equal(item.licensed, false);
    assert.equal(item.locked, true);
    assert.equal(item.action, 'contact_sales');
});


test('licensed installed and licensed not installed differ only in action', () => {
    const installed = tile(
        tileViewModel(
            makeClaims('fcs'),
            NOW,
            ['fcs'],
        ),
        'fcs',
    );

    const notInstalled = tile(
        tileViewModel(
            makeClaims('fcs'),
            NOW,
            [],
        ),
        'fcs',
    );

    const installedWithoutAction = {
        ...installed,
        action: undefined,
    };

    const notInstalledWithoutAction = {
        ...notInstalled,
        action: undefined,
    };

    assert.deepEqual(
        installedWithoutAction,
        notInstalledWithoutAction,
    );

    assert.equal(
        installed.action,
        'launch',
    );

    assert.equal(
        notInstalled.action,
        'install',
    );
});


/*
 * --------------------------------------------------------------------------
 * Not licensed
 * --------------------------------------------------------------------------
 */


test('not licensed tile is visible and greyed', () => {
    const result = tileViewModel(
        makeClaims('fcs'),
        NOW,
        [],
    );

    const item = tile(result, 'tem');

    assert.equal(item.licensed, false);
    assert.equal(item.locked, true);
    assert.equal(item.action, 'contact_sales');
    assert.equal(item.badge, 'Not licensed');

    assert.match(
        item.tooltip,
        /not licensed/i,
    );
});


test('not licensed modules are never hidden', () => {
    const result = tileViewModel(
        makeClaims(''),
        NOW,
        [],
    );

    assert.equal(result.length, 6);

    assert.ok(
        result.every(
            (item) => item.locked === true,
        ),
    );
});


/*
 * --------------------------------------------------------------------------
 * Expiry
 * --------------------------------------------------------------------------
 */


test('future expiry is valid', () => {
    const state = getLicenseState(
        makeClaims('fcs', {
            license_expires:
                '2026-08-20T10:00:01.000Z',
        }),
        NOW,
    );

    assert.deepEqual(
        state,
        {
            valid: true,
            expired: false,
            malformed: false,
        },
    );
});


test('exact expiry time is expired', () => {
    const state = getLicenseState(
        makeClaims('fcs', {
            license_expires:
                '2026-08-20T10:00:00.000Z',
        }),
        NOW,
    );

    assert.deepEqual(
        state,
        {
            valid: false,
            expired: true,
            malformed: false,
        },
    );
});


test('past expiry is expired', () => {
    const state = getLicenseState(
        makeClaims('fcs', {
            license_expires:
                '2026-08-20T09:59:59.999Z',
        }),
        NOW,
    );

    assert.equal(state.expired, true);
});


test('expired licence locks every tile', () => {
    const result = tileViewModel(
        makeClaims(
            'fcs,nta,tem,western,cross_compare,ai_chat',
            {
                license_expires:
                    '2026-08-19T10:00:00.000Z',
            },
        ),
        NOW,
        [
            'fcs',
            'nta',
            'tem',
        ],
    );

    assert.equal(result.length, 6);

    assert.ok(
        result.every(
            (item) => item.locked === true,
        ),
    );

    assert.ok(
        result.every(
            (item) => item.licensed === false,
        ),
    );

    assert.ok(
        result.every(
            (item) => item.action === 'contact_sales',
        ),
    );

    assert.ok(
        result.every(
            (item) => item.badge === 'Expired',
        ),
    );

    assert.ok(
        result.every(
            (item) => /expired/i.test(item.tooltip),
        ),
    );
});


test('expired tooltip differs from never licensed tooltip', () => {
    const expired = tile(
        tileViewModel(
            makeClaims('fcs', {
                license_expires:
                    '2026-08-19T10:00:00.000Z',
            }),
            NOW,
            [],
        ),
        'fcs',
    );

    const notLicensed = tile(
        tileViewModel(
            makeClaims(''),
            NOW,
            [],
        ),
        'fcs',
    );

    assert.match(
        expired.tooltip,
        /expired/i,
    );

    assert.match(
        notLicensed.tooltip,
        /not licensed/i,
    );

    assert.notEqual(
        expired.tooltip,
        notLicensed.tooltip,
    );
});


test('perpetual licence does not expire', () => {
    const result = tileViewModel(
        makeClaims('fcs', {
            license_expires: 'perpetual',
        }),
        NOW,
        [],
    );

    assert.equal(
        tile(result, 'fcs').action,
        'install',
    );
});


/*
 * --------------------------------------------------------------------------
 * cross_compare
 * --------------------------------------------------------------------------
 */


test('cross_compare is not licensed when absent from claims', () => {
    const result = tileViewModel(
        makeClaims('fcs,nta'),
        NOW,
        [],
    );

    const item = tile(
        result,
        'cross_compare',
    );

    assert.equal(item.licensed, false);
    assert.equal(item.locked, true);
    assert.equal(item.action, 'contact_sales');
    assert.equal(item.badge, 'Not licensed');

    assert.match(
        item.tooltip,
        /not licensed/i,
    );
});


test('cross_compare is locked when owned but fewer than two base modules exist', () => {
    const result = tileViewModel(
        makeClaims('fcs,cross_compare'),
        NOW,
        [],
    );

    const item = tile(
        result,
        'cross_compare',
    );

    assert.equal(item.licensed, false);
    assert.equal(item.locked, true);
    assert.equal(item.action, 'none');
    assert.equal(
        item.badge,
        'Requires 2 modules',
    );

    assert.match(
        item.tooltip,
        /at least two base modules/i,
    );
});


test('cross_compare becomes usable with two base modules', () => {
    const result = tileViewModel(
        makeClaims('fcs,nta,cross_compare'),
        NOW,
        [],
    );

    const item = tile(
        result,
        'cross_compare',
    );

    assert.equal(item.licensed, true);
    assert.equal(item.locked, false);
    assert.equal(item.action, 'install');
});


test('cross_compare launches when installed', () => {
    const result = tileViewModel(
        makeClaims('fcs,nta,cross_compare'),
        NOW,
        ['cross_compare'],
    );

    const item = tile(
        result,
        'cross_compare',
    );

    assert.equal(item.licensed, true);
    assert.equal(item.locked, false);
    assert.equal(item.action, 'launch');
});


test('three base modules also satisfy cross_compare requirement', () => {
    const result = tileViewModel(
        makeClaims(
            'fcs,nta,tem,cross_compare',
        ),
        NOW,
        [],
    );

    const item = tile(
        result,
        'cross_compare',
    );

    assert.equal(item.licensed, true);
    assert.equal(item.locked, false);
});


test('cross_compare does not count itself as a base module', () => {
    const result = tileViewModel(
        makeClaims('cross_compare'),
        NOW,
        [],
    );

    const item = tile(
        result,
        'cross_compare',
    );

    assert.equal(item.licensed, false);
    assert.equal(item.locked, true);
    assert.equal(item.action, 'none');
});


/*
 * --------------------------------------------------------------------------
 * AI chat
 * --------------------------------------------------------------------------
 */


test('ai_chat follows normal entitlement/install behaviour', () => {
    const notInstalled = tile(
        tileViewModel(
            makeClaims('ai_chat'),
            NOW,
            [],
        ),
        'ai_chat',
    );

    assert.equal(
        notInstalled.action,
        'install',
    );

    const installed = tile(
        tileViewModel(
            makeClaims('ai_chat'),
            NOW,
            ['ai_chat'],
        ),
        'ai_chat',
    );

    assert.equal(
        installed.action,
        'launch',
    );
});


/*
 * --------------------------------------------------------------------------
 * Malformed claims — fail closed
 * --------------------------------------------------------------------------
 */


test('null claims fail closed', () => {
    const result = tileViewModel(
        null,
        NOW,
        [],
    );

    assert.equal(result.length, 6);

    assert.ok(
        result.every(
            (item) => item.locked === true,
        ),
    );

    assert.ok(
        result.every(
            (item) => item.action === 'none',
        ),
    );
});


test('undefined claims fail closed', () => {
    const result = tileViewModel(
        undefined,
        NOW,
        [],
    );

    assert.ok(
        result.every(
            (item) => item.locked === true,
        ),
    );

    assert.ok(
        result.every(
            (item) => item.action === 'none',
        ),
    );
});


test('numeric claims fail closed', () => {
    const result = tileViewModel(
        123,
        NOW,
        [],
    );

    assert.equal(result.length, 6);

    assert.ok(
        result.every(
            (item) => item.action === 'none',
        ),
    );
});


test('string claims fail closed', () => {
    const result = tileViewModel(
        'malformed',
        NOW,
        [],
    );

    assert.ok(
        result.every(
            (item) => item.locked === true,
        ),
    );
});


test('modules numeric value fails closed', () => {
    const result = tileViewModel(
        makeClaims(123),
        NOW,
        [],
    );

    assert.ok(
        result.every(
            (item) => item.action === 'none',
        ),
    );
});


test('modules object value fails closed', () => {
    const result = tileViewModel(
        makeClaims({
            fcs: true,
        }),
        NOW,
        [],
    );

    assert.ok(
        result.every(
            (item) => item.action === 'none',
        ),
    );
});


test('modules array containing non-string fails closed', () => {
    const result = tileViewModel(
        makeClaims([
            'fcs',
            123,
        ]),
        NOW,
        [],
    );

    assert.ok(
        result.every(
            (item) => item.action === 'none',
        ),
    );
});


test('invalid expiry fails closed', () => {
    const result = tileViewModel(
        makeClaims('fcs', {
            license_expires:
                'definitely-not-a-date',
        }),
        NOW,
        [],
    );

    assert.ok(
        result.every(
            (item) => item.locked === true,
        ),
    );

    assert.ok(
        result.every(
            (item) => item.action === 'none',
        ),
    );
});


test('invalid now fails closed', () => {
    const result = tileViewModel(
        makeClaims('fcs'),
        new Date('invalid'),
        [],
    );

    assert.ok(
        result.every(
            (item) => item.action === 'none',
        ),
    );
});


test('installedSkus must be an array', () => {
    const result = tileViewModel(
        makeClaims('fcs'),
        NOW,
        null,
    );

    assert.ok(
        result.every(
            (item) => item.action === 'none',
        ),
    );
});


test('installedSkus containing malformed values fails closed', () => {
    const result = tileViewModel(
        makeClaims('fcs'),
        NOW,
        ['fcs', 123],
    );

    assert.ok(
        result.every(
            (item) => item.action === 'none',
        ),
    );
});


/*
 * --------------------------------------------------------------------------
 * Non-mutation
 * --------------------------------------------------------------------------
 */


test('does not mutate claims', () => {
    const input = makeClaims([
        'fcs',
        'nta',
        'cross_compare',
    ]);

    const original = JSON.parse(
        JSON.stringify(input),
    );

    tileViewModel(
        input,
        NOW,
        [],
    );

    assert.deepEqual(
        input,
        original,
    );
});


test('does not mutate installedSkus', () => {
    const installed = [
        'fcs',
        'nta',
    ];

    const original = [
        ...installed,
    ];

    tileViewModel(
        makeClaims('fcs,nta'),
        NOW,
        installed,
    );

    assert.deepEqual(
        installed,
        original,
    );
});


/*
 * --------------------------------------------------------------------------
 * Determinism
 * --------------------------------------------------------------------------
 */


test('repeated evaluation produces the same result', () => {
    const input = makeClaims(
        'fcs,nta,cross_compare,ai_chat',
    );

    const first = tileViewModel(
        input,
        NOW,
        ['fcs'],
    );

    const second = tileViewModel(
        input,
        NOW,
        ['fcs'],
    );

    assert.deepEqual(
        first,
        second,
    );
});


/*
 * --------------------------------------------------------------------------
 * Output contract
 * --------------------------------------------------------------------------
 */


test('every tile has the required output fields', () => {
    const result = tileViewModel(
        makeClaims('fcs,nta'),
        NOW,
        ['fcs'],
    );

    for (const item of result) {
        assert.equal(
            typeof item.sku,
            'string',
        );

        assert.equal(
            typeof item.label,
            'string',
        );

        assert.equal(
            typeof item.licensed,
            'boolean',
        );

        assert.equal(
            typeof item.locked,
            'boolean',
        );

        assert.ok(
            item.badge === null ||
            typeof item.badge === 'string',
        );

        assert.equal(
            typeof item.tooltip,
            'string',
        );

        assert.ok(
            [
                'launch',
                'install',
                'contact_sales',
                'none',
            ].includes(item.action),
        );
    }
});


test('licensed tiles are never locked', () => {
    const result = tileViewModel(
        makeClaims(
            'fcs,nta,tem,western,ai_chat',
        ),
        NOW,
        [],
    );

    for (const item of result) {
        if (item.licensed) {
            assert.equal(
                item.locked,
                false,
            );

            assert.ok(
                item.action === 'launch' ||
                item.action === 'install',
            );
        }
    }
});


test('locked tiles never launch or install', () => {
    const result = tileViewModel(
        makeClaims('fcs'),
        NOW,
        ['fcs'],
    );

    for (const item of result) {
        if (item.locked) {
            assert.ok(
                item.action === 'contact_sales' ||
                item.action === 'none',
            );
        }
    }
});