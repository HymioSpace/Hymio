import type { Command, OathEvent } from '@hymio/protocol';
export interface Pending {
  id: string;
  account: string;
  command: Command;
  at: number;
}
let database: Promise<IDBDatabase> | undefined;
function db() {
  return (database ??= new Promise<IDBDatabase>((resolve, reject) => {
    const request = indexedDB.open('hymio-client', 1);
    request.onupgradeneeded = () => {
      const store = request.result.createObjectStore('events', { keyPath: 'key' });
      store.createIndex('account', 'account');
      const commands = request.result.createObjectStore('commands', { keyPath: 'id' });
      commands.createIndex('account', 'account');
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => {
      database = undefined;
      reject(request.error);
    };
    request.onblocked = () => reject(new Error('请关闭旧版 Hymio 页面后重试'));
  }));
}
async function write(store: string, operation: (store: IDBObjectStore) => void) {
  const database = await db();
  return new Promise<void>((resolve, reject) => {
    const tx = database.transaction(store, 'readwrite');
    operation(tx.objectStore(store));
    tx.oncomplete = () => resolve();
    tx.onabort = tx.onerror = () => reject(tx.error ?? new Error('本机记录保存失败'));
  });
}
async function read<T>(store: string, account: string): Promise<T[]> {
  const database = await db();
  return new Promise((resolve, reject) => {
    const request = database.transaction(store).objectStore(store).index('account').getAll(account);
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}
export const storage = {
  saveEvent: (account: string, event: OathEvent) =>
    write('events', (s) => s.put({ key: `${account}:${event.event_seq}`, account, event })),
  events: async (account: string) =>
    (await read<{ event: OathEvent }>('events', account))
      .map((e) => e.event)
      .sort((a, b) => a.event_seq - b.event_seq),
  saveCommand: (pending: Pending) => write('commands', (s) => s.put(pending)),
  removeCommand: (id: string) => write('commands', (s) => s.delete(id)),
  commands: async (account: string) =>
    (await read<Pending>('commands', account)).sort((a, b) => a.at - b.at),
};
