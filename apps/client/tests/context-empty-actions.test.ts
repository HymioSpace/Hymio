import { test } from 'node:test';
import assert from 'node:assert/strict';
import { contextEmptyAction } from '../src/contextModel.ts';

const base = { layer: 'records' as const, category: 'all', source: 'all', query: '', recordCount: 0 };
test('empty footprints open collection instead of selecting their current tab', () => {
  assert.equal(contextEmptyAction(base), 'collect');
  assert.equal(contextEmptyAction({ ...base, recordCount: 10 }), 'collect');
});
test('empty understanding can navigate to available footprints', () => {
  assert.equal(contextEmptyAction({ ...base, layer: 'artifacts', recordCount: 2 }), 'records');
  assert.equal(contextEmptyAction({ ...base, layer: 'artifacts' }), 'collect');
});
test('active source, category and query filters are cleared before navigation', () => {
  assert.equal(contextEmptyAction({ ...base, source: 'connector' }), 'clear');
  assert.equal(contextEmptyAction({ ...base, layer: 'artifacts', category: 'work', recordCount: 2 }), 'clear');
  assert.equal(contextEmptyAction({ ...base, query: 'missing' }), 'clear');
});
