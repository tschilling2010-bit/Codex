// HefterPro persistence via IndexedDB — ES5-safe
// Automatically caches profile backups in the browser and restores on empty server.

var ProfileCache = (function () {
  var DB_NAME = "hefterpro";
  var DB_VERSION = 1;
  var STORE = "backups";

  function openDB(cb) {
    var req = indexedDB.open(DB_NAME, DB_VERSION);
    req.onupgradeneeded = function () {
      var db = req.result;
      if (!db.objectStoreNames.contains(STORE)) {
        db.createObjectStore(STORE, { keyPath: "id" });
      }
    };
    req.onsuccess = function () { cb(null, req.result); };
    req.onerror = function () { cb(req.error, null); };
  }

  function saveBackup(profileId, cb) {
    fetch("/api/handwriting/profile/" + profileId + "/backup")
      .then(function (res) {
        if (!res.ok) throw new Error("Backup fehlgeschlagen");
        return res.blob();
      })
      .then(function (blob) {
        openDB(function (err, db) {
          if (err) { if (cb) cb(err); return; }
          var tx = db.transaction(STORE, "readwrite");
          var store = tx.objectStore(STORE);
          store.put({ id: profileId, blob: blob, ts: Date.now() });
          tx.oncomplete = function () { if (cb) cb(null); };
          tx.onerror = function () { if (cb) cb(tx.error); };
        });
      })
      .catch(function (e) { if (cb) cb(e); });
  }

  function getAllBackups(cb) {
    openDB(function (err, db) {
      if (err) { cb(err, []); return; }
      var tx = db.transaction(STORE, "readonly");
      var store = tx.objectStore(STORE);
      var req = store.getAll();
      req.onsuccess = function () { cb(null, req.result || []); };
      req.onerror = function () { cb(req.error, []); };
    });
  }

  function restoreAll(cb) {
    getAllBackups(function (err, backups) {
      if (err || !backups.length) { if (cb) cb(0); return; }
      var done = 0;
      var total = backups.length;
      backups.forEach(function (entry) {
        var fd = new FormData();
        fd.append("file", entry.blob, "backup.zip");
        fetch("/api/handwriting/profile/restore", { method: "POST", body: fd })
          .then(function () { done++; if (done === total && cb) cb(done); })
          .catch(function () { done++; if (done === total && cb) cb(done); });
      });
    });
  }

  function removeBackup(profileId, cb) {
    openDB(function (err, db) {
      if (err) { if (cb) cb(err); return; }
      var tx = db.transaction(STORE, "readwrite");
      tx.objectStore(STORE).delete(profileId);
      tx.oncomplete = function () { if (cb) cb(null); };
    });
  }

  return {
    save: saveBackup,
    restoreAll: restoreAll,
    remove: removeBackup
  };
})();
