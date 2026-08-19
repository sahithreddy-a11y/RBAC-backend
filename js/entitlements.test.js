'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');

const {
  BASE_MODULES,
  ADDON_MODULES,
  ALL_MODULES,
  normalizeModules,
  evaluateLicense,
  isLicensed,
  tileStates,
} = require('./entitlements');

const NOW = new Date('2026-08-19T10:00:00.000Z');

function activeClaims(
  modules,
  overrides = {},
) {
  return {
    modules,
    license_status: 'active',
    license_expires: '2026-12-31T23:59:59.000Z',
    ...overrides,
  };
}

function perpetualClaims(
  modules,
  overrides = {},
) {
  return {
    modules,
    license_status: 'perpetual',
    ...overrides,
  };
}

function getTile(states, sku) {
  const tile = states.find(
    (item) => item.sku === sku,
  );

  assert.ok(
    tile,
    `Expected tile ${sku} to exist`,
  );

  return tile;
}

/* ---------------------------------------------------------
 * Catalogue
 * --------------------------------------------------------- */

test('base module catalogue is fixed', () => {
  assert.deepEqual(
    BASE_MODULES,
    ['fcs', 'nta', 'tem', 'western'],
  );
});

test('addon catalogue is fixed', () => {
  assert.deepEqual(
    ADDON_MODULES,
    ['cross_compare', 'ai_chat'],
  );
});

test('all known modules are present exactly once', () => {
  assert.deepEqual(
    ALL_MODULES,
    [
      'fcs',
      'nta',
      'tem',
      'western',
      'cross_compare',
      'ai_chat',
    ],
  );

  assert.equal(
    new Set(ALL_MODULES).size,
    ALL_MODULES.length,
  );
});

/* ---------------------------------------------------------
 * Normalization
 * --------------------------------------------------------- */

test('comma-separated string and array claims are equivalent', () => {
  const stringResult = tileStates(
    activeClaims('fcs,nta'),
    NOW,
  );

  const arrayResult = tileStates(
    activeClaims(['fcs', 'nta']),
    NOW,
  );

  assert.deepEqual(
    arrayResult,
    stringResult,
  );
});

test('module strings are trimmed and lowercased', () => {
  const result = normalizeModules(
    ' FCS , NTA , TeM ',
  );

  assert.deepEqual(
    [...result],
    ['fcs', 'nta', 'tem'],
  );
});

test('array module values are trimmed and lowercased', () => {
  const result = normalizeModules([
    ' FCS ',
    'NTA',
    ' tem ',
  ]);

  assert.deepEqual(
    [...result],
    ['fcs', 'nta', 'tem'],
  );
});

test('duplicate module claims are deduplicated', () => {
  const result = normalizeModules(
    'fcs,FCS, nta,nta',
  );

  assert.deepEqual(
    [...result],
    ['fcs', 'nta'],
  );
});

test('empty string is a valid empty entitlement list', () => {
  const result = normalizeModules('');

  assert.ok(result instanceof Set);
  assert.equal(result.size, 0);
});

test('empty array is a valid empty entitlement list', () => {
  const result = normalizeModules([]);

  assert.ok(result instanceof Set);
  assert.equal(result.size, 0);
});

/* ---------------------------------------------------------
 * Malformed module claims
 * --------------------------------------------------------- */

test('non-string and non-array module claims fail closed', () => {
  for (const value of [
    null,
    undefined,
    0,
    1,
    false,
    true,
    {},
    { modules: ['fcs'] },
  ]) {
    assert.equal(
      normalizeModules(value),
      null,
    );
  }
});

test('array containing a non-string fails closed', () => {
  assert.equal(
    normalizeModules([
      'fcs',
      42,
      'nta',
    ]),
    null,
  );
});

test('array containing null fails closed', () => {
  assert.equal(
    normalizeModules([
      'fcs',
      null,
      'nta',
    ]),
    null,
  );
});

test('blank array element fails closed', () => {
  assert.equal(
    normalizeModules([
      'fcs',
      '   ',
      'nta',
    ]),
    null,
  );
});

test('blank comma-separated element fails closed', () => {
  assert.equal(
    normalizeModules('fcs,,nta'),
    null,
  );
});

test('leading comma fails closed', () => {
  assert.equal(
    normalizeModules(',fcs'),
    null,
  );
});

test('trailing comma fails closed', () => {
  assert.equal(
    normalizeModules('fcs,'),
    null,
  );
});

/* ---------------------------------------------------------
 * Licence status
 * --------------------------------------------------------- */

test('active licence is usable before expiry', () => {
  const result = evaluateLicense(
    activeClaims(['fcs']),
    NOW,
  );

  assert.equal(result.usable, true);
  assert.equal(result.reason, 'licensed');
});

test('active licence is expired at exact expiry instant', () => {
  const claims = activeClaims(
    ['fcs'],
    {
      license_expires:
        '2026-08-19T10:00:00.000Z',
    },
  );

  const result = evaluateLicense(
    claims,
    NOW,
  );

  assert.equal(result.usable, false);
  assert.equal(
    result.reason,
    'license_expired',
  );
});

test('active licence is valid one millisecond before expiry', () => {
  const claims = activeClaims(
    ['fcs'],
    {
      license_expires:
        '2026-08-19T10:00:00.001Z',
    },
  );

  const result = evaluateLicense(
    claims,
    NOW,
  );

  assert.equal(result.usable, true);
});

test('expired status locks licence immediately', () => {
  const result = evaluateLicense(
    activeClaims(
      ['fcs'],
      {
        license_status: 'expired',
      },
    ),
    NOW,
  );

  assert.equal(result.usable, false);
  assert.equal(
    result.reason,
    'license_expired',
  );
});

test('revoked status locks licence', () => {
  const result = evaluateLicense(
    activeClaims(
      ['fcs'],
      {
        license_status: 'revoked',
      },
    ),
    NOW,
  );

  assert.equal(result.usable, false);
  assert.equal(
    result.reason,
    'license_revoked',
  );
});

test('suspended status locks licence', () => {
  const result = evaluateLicense(
    activeClaims(
      ['fcs'],
      {
        license_status: 'suspended',
      },
    ),
    NOW,
  );

  assert.equal(result.usable, false);
  assert.equal(
    result.reason,
    'license_suspended',
  );
});

test('invalid status locks licence', () => {
  const result = evaluateLicense(
    activeClaims(
      ['fcs'],
      {
        license_status: 'invalid',
      },
    ),
    NOW,
  );

  assert.equal(result.usable, false);
  assert.equal(
    result.reason,
    'license_invalid',
  );
});

test('unknown licence status fails closed', () => {
  const result = evaluateLicense(
    activeClaims(
      ['fcs'],
      {
        license_status: 'future_status',
      },
    ),
    NOW,
  );

  assert.equal(result.usable, false);
  assert.equal(
    result.reason,
    'license_unusable',
  );
});

test('missing licence status fails closed', () => {
  const claims = {
    modules: ['fcs'],
    license_expires:
      '2026-12-31T23:59:59.000Z',
  };

  const result = evaluateLicense(
    claims,
    NOW,
  );

  assert.equal(result.usable, false);
});

test('non-string licence status fails closed', () => {
  for (const status of [
    null,
    undefined,
    123,
    true,
    {},
    [],
  ]) {
    const result = evaluateLicense(
      activeClaims(
        ['fcs'],
        {
          license_status: status,
        },
      ),
      NOW,
    );

    assert.equal(result.usable, false);
  }
});

test('active licence without expiry fails closed', () => {
  const claims = {
    modules: ['fcs'],
    license_status: 'active',
  };

  const result = evaluateLicense(
    claims,
    NOW,
  );

  assert.equal(result.usable, false);
});

test('active licence with malformed expiry fails closed', () => {
  const result = evaluateLicense(
    activeClaims(
      ['fcs'],
      {
        license_expires: 'not-a-date',
      },
    ),
    NOW,
  );

  assert.equal(result.usable, false);
});

test('active licence with empty expiry fails closed', () => {
  const result = evaluateLicense(
    activeClaims(
      ['fcs'],
      {
        license_expires: '   ',
      },
    ),
    NOW,
  );

  assert.equal(result.usable, false);
});

test('perpetual licence does not require expiry', () => {
  const result = evaluateLicense(
    perpetualClaims(['fcs']),
    NOW,
  );

  assert.equal(result.usable, true);
  assert.equal(result.reason, 'licensed');
});

/* ---------------------------------------------------------
 * Base modules
 * --------------------------------------------------------- */

test('each base module requires explicit entitlement', () => {
  for (const sku of BASE_MODULES) {
    const claims = activeClaims([sku]);

    assert.equal(
      isLicensed(claims, sku, NOW),
      true,
    );
  }
});

test('unlicensed base modules are denied', () => {
  const claims = activeClaims(['fcs']);

  for (const sku of BASE_MODULES) {
    assert.equal(
      isLicensed(claims, sku, NOW),
      sku === 'fcs',
    );
  }
});

/* ---------------------------------------------------------
 * cross_compare
 * --------------------------------------------------------- */

test('cross_compare requires explicit entitlement', () => {
  const claims = activeClaims([
    'fcs',
    'nta',
  ]);

  assert.equal(
    isLicensed(
      claims,
      'cross_compare',
      NOW,
    ),
    false,
  );
});

test('cross_compare with one base module is denied', () => {
  const claims = activeClaims([
    'fcs',
    'cross_compare',
  ]);

  assert.equal(
    isLicensed(
      claims,
      'cross_compare',
      NOW,
    ),
    false,
  );
});

test('cross_compare with two base modules is granted', () => {
  const claims = activeClaims([
    'fcs',
    'nta',
    'cross_compare',
  ]);

  assert.equal(
    isLicensed(
      claims,
      'cross_compare',
      NOW,
    ),
    true,
  );
});

test('cross_compare with all four base modules is granted', () => {
  const claims = activeClaims([
    'fcs',
    'nta',
    'tem',
    'western',
    'cross_compare',
  ]);

  assert.equal(
    isLicensed(
      claims,
      'cross_compare',
      NOW,
    ),
    true,
  );
});

test('unknown modules do not count toward cross_compare dependency', () => {
  const claims = activeClaims([
    'fcs',
    'unknown',
    'cross_compare',
  ]);

  assert.equal(
    isLicensed(
      claims,
      'cross_compare',
      NOW,
    ),
    false,
  );
});

/* ---------------------------------------------------------
 * ai_chat
 * --------------------------------------------------------- */

test('ai_chat requires explicit entitlement', () => {
  const claims = activeClaims([
    'fcs',
    'nta',
  ]);

  assert.equal(
    isLicensed(
      claims,
      'ai_chat',
      NOW,
    ),
    false,
  );
});

test('ai_chat is granted when explicitly licensed', () => {
  const claims = activeClaims([
    'fcs',
    'ai_chat',
  ]);

  assert.equal(
    isLicensed(
      claims,
      'ai_chat',
      NOW,
    ),
    true,
  );
});

/* ---------------------------------------------------------
 * Unknown SKU protection
 * --------------------------------------------------------- */

test('unknown SKU can never be licensed', () => {
  const claims = activeClaims([
    'fcs',
    'nta',
    'unknown',
    'admin',
    'superuser',
  ]);

  for (const sku of [
    'unknown',
    'admin',
    'superuser',
    '',
    ' ',
    null,
    undefined,
    123,
  ]) {
    assert.equal(
      isLicensed(
        claims,
        sku,
        NOW,
      ),
      false,
    );
  }
});

test('unknown SKUs never appear as launcher tiles', () => {
  const claims = activeClaims([
    'fcs',
    'nta',
    'unknown',
    'admin',
  ]);

  const states = tileStates(
    claims,
    NOW,
  );

  assert.deepEqual(
    states.map((tile) => tile.sku),
    ALL_MODULES,
  );

  assert.equal(
    states.some(
      (tile) => tile.sku === 'unknown',
    ),
    false,
  );

  assert.equal(
    states.some(
      (tile) => tile.sku === 'admin',
    ),
    false,
  );
});

/* ---------------------------------------------------------
 * Expiry / locking behaviour
 * --------------------------------------------------------- */

test('expired licence locks every known tile', () => {
  const states = tileStates(
    activeClaims(
      [
        'fcs',
        'nta',
        'tem',
        'western',
        'cross_compare',
        'ai_chat',
      ],
      {
        license_expires:
          '2026-08-18T23:59:59.999Z',
      },
    ),
    NOW,
  );

  assert.equal(
    states.length,
    ALL_MODULES.length,
  );

  for (const tile of states) {
    assert.equal(tile.licensed, false);
    assert.equal(tile.locked, true);
    assert.equal(
      tile.reason,
      'license_expired',
    );
  }
});

test('revoked licence locks every known tile', () => {
  const states = tileStates(
    activeClaims(
      ['fcs', 'nta'],
      {
        license_status: 'revoked',
      },
    ),
    NOW,
  );

  assert.equal(
    states.length,
    ALL_MODULES.length,
  );

  for (const tile of states) {
    assert.equal(tile.licensed, false);
    assert.equal(tile.locked, true);
    assert.equal(
      tile.reason,
      'license_revoked',
    );
  }
});

test('expired licence does not hide tiles', () => {
  const states = tileStates(
    activeClaims(
      ['fcs'],
      {
        license_expires:
          '2026-08-18T00:00:00.000Z',
      },
    ),
    NOW,
  );

  assert.deepEqual(
    states.map((tile) => tile.sku),
    ALL_MODULES,
  );
});

/* ---------------------------------------------------------
 * Malformed claims
 * --------------------------------------------------------- */

test('null claims fail closed without throwing', () => {
  assert.doesNotThrow(() => {
    tileStates(null, NOW);
  });

  const states = tileStates(
    null,
    NOW,
  );

  assert.equal(
    states.length,
    ALL_MODULES.length,
  );

  for (const tile of states) {
    assert.equal(tile.licensed, false);
    assert.equal(tile.locked, true);
    assert.equal(
      tile.reason,
      'invalid_claims',
    );
  }
});

test('undefined claims fail closed without throwing', () => {
  const states = tileStates(
    undefined,
    NOW,
  );

  for (const tile of states) {
    assert.equal(tile.licensed, false);
    assert.equal(tile.locked, true);
  }
});

test('primitive claims fail closed without throwing', () => {
  for (const claims of [
    '',
    'claims',
    0,
    1,
    true,
    false,
    [],
  ]) {
    assert.doesNotThrow(() => {
      tileStates(claims, NOW);
    });

    const states = tileStates(
      claims,
      NOW,
    );

    assert.equal(
      states.length,
      ALL_MODULES.length,
    );

    for (const tile of states) {
      assert.equal(tile.licensed, false);
      assert.equal(tile.locked, true);
    }
  }
});

test('array claims fail closed', () => {
  const states = tileStates(
    ['fcs', 'nta'],
    NOW,
  );

  for (const tile of states) {
    assert.equal(tile.licensed, false);
    assert.equal(tile.locked, true);
  }
});

test('malformed modules claim locks every tile', () => {
  const malformedClaims = [
    null,
    undefined,
    123,
    true,
    {},
    ['fcs', 123],
    ['fcs', null],
    ['fcs', ''],
    'fcs,,nta',
  ];

  for (const modules of malformedClaims) {
    const states = tileStates(
      activeClaims(modules),
      NOW,
    );

    assert.equal(
      states.length,
      ALL_MODULES.length,
    );

    for (const tile of states) {
      assert.equal(tile.licensed, false);
      assert.equal(tile.locked, true);
      assert.equal(
        tile.reason,
        'invalid_claims',
      );
    }
  }
});

/* ---------------------------------------------------------
 * Clock injection
 * --------------------------------------------------------- */

test('clock is evaluated from injected now', () => {
  const claims = activeClaims(
    ['fcs'],
    {
      license_expires:
        '2026-08-20T00:00:00.000Z',
    },
  );

  assert.equal(
    isLicensed(
      claims,
      'fcs',
      new Date(
        '2026-08-19T23:59:59.999Z',
      ),
    ),
    true,
  );

  assert.equal(
    isLicensed(
      claims,
      'fcs',
      new Date(
        '2026-08-20T00:00:00.000Z',
      ),
    ),
    false,
  );
});

test('missing now fails closed', () => {
  const claims = activeClaims(['fcs']);

  const states = tileStates(
    claims,
    undefined,
  );

  for (const tile of states) {
    assert.equal(tile.licensed, false);
    assert.equal(tile.locked, true);
  }
});

test('invalid Date fails closed', () => {
  const claims = activeClaims(['fcs']);

  const states = tileStates(
    claims,
    new Date('not-valid'),
  );

  for (const tile of states) {
    assert.equal(tile.licensed, false);
    assert.equal(tile.locked, true);
  }
});

/* ---------------------------------------------------------
 * Output contract
 * --------------------------------------------------------- */

test('tileStates always returns all known tiles', () => {
  const states = tileStates(
    activeClaims(['fcs']),
    NOW,
  );

  assert.equal(
    states.length,
    ALL_MODULES.length,
  );

  assert.deepEqual(
    states.map((tile) => tile.sku),
    ALL_MODULES,
  );
});

test('tile output has the expected fields and types', () => {
  const states = tileStates(
    activeClaims(['fcs']),
    NOW,
  );

  for (const tile of states) {
    assert.deepEqual(
      Object.keys(tile).sort(),
      [
        'licensed',
        'locked',
        'reason',
        'sku',
      ],
    );

    assert.equal(
      typeof tile.sku,
      'string',
    );

    assert.equal(
      typeof tile.licensed,
      'boolean',
    );

    assert.equal(
      typeof tile.locked,
      'boolean',
    );

    assert.equal(
      typeof tile.reason,
      'string',
    );
  }
});

test('licensed tiles are never simultaneously locked', () => {
  const states = tileStates(
    activeClaims([
      'fcs',
      'nta',
      'ai_chat',
    ]),
    NOW,
  );

  for (const tile of states) {
    assert.notEqual(
      tile.licensed && tile.locked,
      true,
    );
  }
});

test('locked tiles are never reported as licensed', () => {
  const states = tileStates(
    activeClaims(['fcs']),
    NOW,
  );

  for (const tile of states) {
    if (tile.locked) {
      assert.equal(
        tile.licensed,
        false,
      );
    }
  }
});