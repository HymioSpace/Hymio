export function executionDevices<T extends { kind: string }>(devices: T[]) {
  return devices.filter((device) => !['ios', 'web'].includes(device.kind));
}
