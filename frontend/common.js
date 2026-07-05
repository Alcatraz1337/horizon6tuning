// horizon6tuning shared client helpers + tiny event bus.
// Loaded by every page; exposes window.$, window.fetchJSON, window.bus.
"use strict";

(function () {
  window.$ = (id) => document.getElementById(id);

  window.fetchJSON = async function (url, opts) {
    const r = await fetch(url, opts);
    const text = await r.text();
    let data = null;
    if (text) {
      try { data = JSON.parse(text); } catch { data = { detail: text }; }
    }
    if (!r.ok) {
      const msg = (data && (data.detail || data.error)) || `HTTP ${r.status}`;
      const err = new Error(msg);
      err.status = r.status;
      err.data = data;
      throw err;
    }
    return data;
  };

  // tiny pub/sub for cross-view state (current setup, active view)
  const subs = new Map();
  window.bus = {
    on(evt, fn) {
      if (!subs.has(evt)) subs.set(evt, new Set());
      subs.get(evt).add(fn);
      return () => subs.get(evt).delete(fn);
    },
    emit(evt, payload) {
      const set = subs.get(evt);
      if (set) for (const fn of set) { try { fn(payload); } catch (e) { console.warn(e); } }
    },
  };
})();