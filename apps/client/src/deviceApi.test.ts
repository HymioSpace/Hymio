import assert from 'node:assert/strict';
import test from 'node:test';
import { executionDevices } from './deviceFilters.ts';

function device(kind: string, id = kind) {
  return {
    device_id: id,
    name: id,
    kind,
    provider: 'test',
    state: 'online',
    online: true,
    capabilities: [],
    preserves_files_on_revoke: true,
  };
}

test('device settings only expose execution targets', () => {
  const values = [
    device('ios'),
    device('web'),
    device('personal_mac'),
    device('personal_android', 'android'),
    device('cloud_desktop'),
  ];
  assert.deepEqual(
    executionDevices(values).map((item) => item.kind),
    ['personal_mac', 'personal_android', 'cloud_desktop'],
  );
});
