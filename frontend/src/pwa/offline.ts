import { apiRequest } from '@/api/client';

type CachedResponse = { key: string; value: unknown; savedAt: number };
export type OfflineAction = {
  id: string;
  scope: string;
  kind: 'purchase-request' | 'goods-received-note';
  path: string;
  body: Record<string, unknown>;
  createdAt: number;
  state: 'queued' | 'syncing' | 'attention';
  error?: string;
};

const DB = 'construct-offline';
const VERSION = 1;
const CACHE = 'responses';
const OUTBOX = 'outbox';
let syncing = false;

function database(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DB, VERSION);
    request.onupgradeneeded = () => {
      const db = request.result;
      if (!db.objectStoreNames.contains(CACHE)) db.createObjectStore(CACHE, { keyPath: 'key' });
      if (!db.objectStoreNames.contains(OUTBOX)) db.createObjectStore(OUTBOX, { keyPath: 'id' });
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

async function read<T>(store: string, key: IDBValidKey): Promise<T | undefined> {
  const db = await database();
  return new Promise((resolve, reject) => {
    const request = db.transaction(store, 'readonly').objectStore(store).get(key);
    request.onsuccess = () => resolve(request.result as T | undefined);
    request.onerror = () => reject(request.error);
  });
}
async function all<T>(store: string): Promise<T[]> {
  const db = await database();
  return new Promise((resolve, reject) => {
    const request = db.transaction(store, 'readonly').objectStore(store).getAll();
    request.onsuccess = () => resolve(request.result as T[]);
    request.onerror = () => reject(request.error);
  });
}
async function write(store: string, value: unknown): Promise<void> {
  const db = await database();
  return new Promise((resolve, reject) => {
    const request = db.transaction(store, 'readwrite').objectStore(store).put(value);
    request.onsuccess = () => resolve(); request.onerror = () => reject(request.error);
  });
}
async function remove(store: string, key: IDBValidKey): Promise<void> {
  const db = await database();
  return new Promise((resolve, reject) => {
    const request = db.transaction(store, 'readwrite').objectStore(store).delete(key);
    request.onsuccess = () => resolve(); request.onerror = () => reject(request.error);
  });
}
function emit() { window.dispatchEvent(new Event('construct-offline-change')); }

export function offlineScope(access?: string) {
  if (!access) return 'anonymous';
  try { return `user-${JSON.parse(atob(access.split('.')[1].replace(/-/g, '+').replace(/_/g, '/'))).user_id}`; } catch { return 'anonymous'; }
}
export async function cacheResponse(scope: string, key: string, value: unknown) {
  await write(CACHE, { key: `${scope}:${key}`, value, savedAt: Date.now() } satisfies CachedResponse);
}
export async function cachedResponse<T>(scope: string, key: string) {
  return read<CachedResponse>(CACHE, `${scope}:${key}`).then((item) => item?.value as T | undefined);
}
export async function queueOfflineAction(action: Omit<OfflineAction, 'id' | 'createdAt' | 'state'>) {
  const queued: OfflineAction = { ...action, id: crypto.randomUUID(), createdAt: Date.now(), state: 'queued' };
  await write(OUTBOX, queued); emit(); return queued;
}
export async function offlineActions(scope: string) { return (await all<OfflineAction>(OUTBOX)).filter((item) => item.scope === scope).sort((a, b) => a.createdAt - b.createdAt); }
export async function discardOfflineAction(id: string) {
  await remove(OUTBOX, id);
  emit();
}
export async function retryOfflineAction(id: string) {
  const action = await read<OfflineAction>(OUTBOX, id);
  if (!action) return;
  await write(OUTBOX, { ...action, state: 'queued', error: undefined });
  emit();
}
export async function clearOfflineScope(scope: string) {
  const db = await database();
  const tx = db.transaction([CACHE, OUTBOX], 'readwrite');
  for (const storeName of [CACHE, OUTBOX]) {
    const store = tx.objectStore(storeName); const request = store.getAll();
    await new Promise<void>((resolve, reject) => { request.onsuccess = () => { request.result.filter((entry: { key?: string; scope?: string }) => entry.key?.startsWith(`${scope}:`) || entry.scope === scope).forEach((entry: { key?: string; id?: string }) => store.delete(entry.key || entry.id!)); resolve(); }; request.onerror = () => reject(request.error); });
  }
  emit();
}
export async function syncOfflineActions(scope: string) {
  if (syncing || !navigator.onLine) return;
  syncing = true; emit();
  try {
    for (const action of await offlineActions(scope)) {
      if (action.state === 'attention') continue;
      await write(OUTBOX, { ...action, state: 'syncing', error: undefined }); emit();
      try { await apiRequest(action.path, { method: 'POST', body: action.body }); await remove(OUTBOX, action.id); }
      catch (error) {
        const message = error instanceof Error ? error.message : 'Sync failed';
        // A validation/permission conflict must be reviewed; transient network errors retry.
        await write(OUTBOX, { ...action, state: navigator.onLine ? 'attention' : 'queued', error: message });
        if (!navigator.onLine) break;
      }
      emit();
    }
  } finally { syncing = false; emit(); }
}
