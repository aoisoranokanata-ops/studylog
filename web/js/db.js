// IndexedDB の薄いラッパー。外部ライブラリは使わない。

const DB_NAME = 'studylog';
const DB_VERSION = 1;

export const STORES = {
  inbound: { keyPath: 'id' },
  sessions: { keyPath: 'id', indexes: { state: 'state', startedAt: 'startedAt' } },
  mistakes: { keyPath: 'id', indexes: { state: 'state', createdAt: 'createdAt' } },
  reviewResults: { keyPath: 'id', indexes: { state: 'state' } },
  quotaStatus: { keyPath: 'id', indexes: { state: 'state', quotaId: 'quotaId' } },
  outbox: { keyPath: 'packageId', indexes: { sentAt: 'sentAt' } },
  timer: { keyPath: 'id' },
  device: { keyPath: 'id' },
  meta: { keyPath: 'key' },
};

let dbPromise = null;

export function open() {
  if (dbPromise) return dbPromise;
  dbPromise = new Promise((resolve, reject) => {
    const request = indexedDB.open(DB_NAME, DB_VERSION);
    request.onupgradeneeded = () => {
      const db = request.result;
      for (const [name, config] of Object.entries(STORES)) {
        const store = db.objectStoreNames.contains(name)
          ? request.transaction.objectStore(name)
          : db.createObjectStore(name, { keyPath: config.keyPath });
        for (const [indexName, keyPath] of Object.entries(config.indexes || {})) {
          if (!store.indexNames.contains(indexName)) store.createIndex(indexName, keyPath);
        }
      }
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
    request.onblocked = () => reject(new Error('別のタブが開いているため更新できません'));
  });
  return dbPromise;
}

function run(store, mode, action) {
  return open().then(
    (db) =>
      new Promise((resolve, reject) => {
        const transaction = db.transaction(store, mode);
        const request = action(transaction.objectStore(store));
        transaction.onerror = () => reject(transaction.error);
        transaction.onabort = () => reject(transaction.error);
        if (request) {
          request.onsuccess = () => resolve(request.result);
          request.onerror = () => reject(request.error);
        } else {
          transaction.oncomplete = () => resolve();
        }
      }),
  );
}

export const get = (store, key) => run(store, 'readonly', (s) => s.get(key));
export const getAll = (store) => run(store, 'readonly', (s) => s.getAll());
export const put = (store, value) => run(store, 'readwrite', (s) => s.put(value));
export const remove = (store, key) => run(store, 'readwrite', (s) => s.delete(key));
export const clear = (store) => run(store, 'readwrite', (s) => s.clear());
export const count = (store) => run(store, 'readonly', (s) => s.count());

export const getAllByIndex = (store, index, value) =>
  run(store, 'readonly', (s) => s.index(index).getAll(value));

/** 複数ストアをまたぐ更新。fn には {store名: objectStore} を渡す。 */
export function transact(stores, mode, fn) {
  return open().then(
    (db) =>
      new Promise((resolve, reject) => {
        const transaction = db.transaction(stores, mode);
        const handles = {};
        for (const name of stores) handles[name] = transaction.objectStore(name);
        let result;
        try {
          result = fn(handles);
        } catch (error) {
          transaction.abort();
          reject(error);
          return;
        }
        transaction.oncomplete = () => resolve(result);
        transaction.onerror = () => reject(transaction.error);
        transaction.onabort = () => reject(transaction.error);
      }),
  );
}

export async function putMany(store, values) {
  if (!values.length) return;
  await transact([store], 'readwrite', (handles) => {
    for (const value of values) handles[store].put(value);
  });
}

export async function removeMany(store, keys) {
  if (!keys.length) return;
  await transact([store], 'readwrite', (handles) => {
    for (const key of keys) handles[store].delete(key);
  });
}

/** 全消し（設定画面の「データの全削除」用）。 */
export async function wipe() {
  await transact(Object.keys(STORES), 'readwrite', (handles) => {
    for (const store of Object.values(handles)) store.clear();
  });
}

/** 保存領域を消えにくくする。拒否されても動作は続ける。 */
export async function requestPersistence() {
  try {
    if (navigator.storage?.persisted && (await navigator.storage.persisted())) return true;
    if (navigator.storage?.persist) return await navigator.storage.persist();
  } catch {
    /* 未対応の環境では何もしない */
  }
  return false;
}
