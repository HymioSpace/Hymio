type Entry = { id: string; body: unknown; user: string; backend: string };
const key = 'hymio.telemetry.outbox.v1';
let uploading = false;
let queuedFlush: { user: string; backend: string; token: string } | undefined;

function read(): Entry[] {
  try {
    return JSON.parse(localStorage.getItem(key) || '[]') as Entry[];
  } catch {
    return [];
  }
}

export function enqueueTelemetry(entry: Entry, token: string) {
  try {
    const entries = read().filter((item) => item.id !== entry.id);
    localStorage.setItem(key, JSON.stringify([...entries, entry].slice(-100)));
  } catch {
    /* Telemetry cannot block message sending. */
  }
  void flushTelemetry(entry.user, entry.backend, token);
}

export async function flushTelemetry(user: string, backend: string, token: string) {
  if (uploading) {
    queuedFlush = { user, backend, token };
    return;
  }
  uploading = true;
  let target = { user, backend, token };
  try {
    do {
      queuedFlush = undefined;
      for (const entry of read().filter(
        (item) => item.user === target.user && item.backend === target.backend,
      )) {
        try {
          const response = await fetch(`${target.backend.replace(/\/$/, '')}/telemetry/client`, {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
              Authorization: `Bearer ${target.token}`,
            },
            body: JSON.stringify(entry.body),
            signal: AbortSignal.timeout(5000),
            keepalive: true,
          });
          if (!response.ok) break;
          localStorage.setItem(key, JSON.stringify(read().filter((item) => item.id !== entry.id)));
        } catch {
          break;
        }
      }
      target = queuedFlush || target;
    } while (queuedFlush);
  } finally {
    uploading = false;
  }
}
