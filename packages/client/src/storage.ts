import type { Command, OathEvent, ConversationPage } from '@hymio/protocol';
export interface Pending {
  id: string;
  account: string;
  command: Command;
  at: number;
}
let database: Promise<IDBDatabase> | undefined;
function db() {
  return (database ??= new Promise<IDBDatabase>((resolve, reject) => {
    const request = indexedDB.open('hymio-client', 2);
    request.onupgradeneeded = () => {
      const db = request.result;
      if (!db.objectStoreNames.contains('events')) {
        db.createObjectStore('events', { keyPath: 'key' }).createIndex('account', 'account');
        db.createObjectStore('commands', { keyPath: 'id' }).createIndex('account', 'account');
      }
      if (!db.objectStoreNames.contains('snapshots'))
        db.createObjectStore('snapshots', { keyPath: 'account' });
    };
    request.onsuccess = () => {
      request.result.onversionchange = () => request.result.close();
      resolve(request.result);
    };
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
async function snapshot(account: string): Promise<ConversationPage | undefined> {
  const database = await db();
  return new Promise((resolve, reject) => {
    const request = database.transaction('snapshots').objectStore('snapshots').get(account);
    request.onsuccess = () => resolve(request.result?.page);
    request.onerror = () => reject(request.error);
  });
}
async function savePage(account: string, page: ConversationPage, replace: boolean) {
  const database = await db();
  return new Promise<void>((resolve, reject) => {
    const tx = database.transaction(['events', 'snapshots'], 'readwrite');
    const events = tx.objectStore('events');
    const put = () => {
      for (const event of page.events)
        events.put({ key: `${account}:${event.event_seq}`, account, event });
      if (replace) tx.objectStore('snapshots').put({ account, page });
    };
    if (replace) {
      const keys = events.index('account').getAllKeys(account);
      keys.onsuccess = () => {
        for (const key of keys.result) events.delete(key);
        put();
      };
    } else put();
    tx.oncomplete = () => resolve();
    tx.onabort = tx.onerror = () => reject(tx.error ?? new Error('快照保存失败'));
  });
}

export const storage = {
  snapshot,
  savePage,
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
