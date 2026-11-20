import assert from 'node:assert/strict';
import test from 'node:test';
import { workflowLayers } from './workflowLayout.ts';

test('workflow dependency depths form a readable DAG', () => {
  const layers = workflowLayers(
    [
      { id: 'design', depends_on: [] },
      { id: 'backend', depends_on: [] },
      { id: 'review', depends_on: ['design', 'backend'] },
      { id: 'release', depends_on: ['review'] },
    ],
    [],
  );
  assert.deepEqual(
    layers.map((layer) => layer.map((node) => node.id)),
    [['design', 'backend'], ['review'], ['release']],
  );
});

test('workflow layout tolerates a malformed cycle without stalling', () => {
  const layers = workflowLayers(
    [
      { id: 'a', depends_on: ['b'] },
      { id: 'b', depends_on: ['a'] },
    ],
    [],
  );
  assert.deepEqual(layers, [[{ id: 'b', depends_on: ['a'] }], [{ id: 'a', depends_on: ['b'] }]]);
});
