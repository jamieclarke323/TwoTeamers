(() => {
  let database;
  const open = () => {
    if (!database) database = new Promise((resolve, reject) => {
      const request = indexedDB.open("two-teamers-offline-v1", 1);
      request.onupgradeneeded = () => request.result.createObjectStore("games", {keyPath: "id"});
      request.onsuccess = () => resolve(request.result);
      request.onerror = () => reject(request.error);
    });
    return database;
  };
  const update = async (id, change) => {
    const db = await open();
    return new Promise((resolve, reject) => {
      const transaction = db.transaction("games", "readwrite");
      const store = transaction.objectStore("games");
      let result;
      let failure;
      const request = store.get(id);
      request.onsuccess = () => {
        try {
          const changed = change(request.result);
          result = changed.result;
          if (changed.record) store.put(changed.record);
          else store.delete(id);
        } catch (error) {
          failure = error;
          transaction.abort();
        }
      };
      transaction.oncomplete = () => resolve(result);
      transaction.onabort = () => reject(failure || transaction.error);
      transaction.onerror = () => reject(transaction.error);
    });
  };
  const get = async (id) => {
    const db = await open();
    return new Promise((resolve, reject) => {
      const request = db.transaction("games").objectStore("games").get(id);
      request.onsuccess = () => resolve(request.result);
      request.onerror = () => reject(request.error);
    });
  };
  const all = async () => {
    const db = await open();
    return new Promise((resolve, reject) => {
      const request = db.transaction("games").objectStore("games").getAll();
      request.onsuccess = () => resolve(request.result);
      request.onerror = () => reject(request.error);
    });
  };
  globalThis.OfflineStorage = {get, update, all};
})();
