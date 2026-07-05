// horizon6tuning Setups view — list, editor, 9 sections, unit toggle, attach.
// Depends on window.$, window.fetchJSON, window.bus from common.js.
"use strict";

(function () {
  // ---- module state --------------------------------------------------------
  let SCHEMA = null;           // schema payload from /api/setups/schema
  let CURRENT_SETUP_ID = null; // currently attached to session
  let CURRENT_SETUP = null;    // its full dict (or null)
  let LIST = [];               // saved-setups summaries
  let LOADED = null;           // the setup loaded into the editor (dict or {__new:true})
  let FORM = null;             // in-memory edit state mirroring LOADED

  // ---- DOM refs ------------------------------------------------------------
  const $live = $("liveView");
  const $setups = $("setupsView");
  const $tabLive = $("tabLive");
  const $tabSetups = $("tabSetups");
  const $chip = $("currentSetupChip");
  const $chipName = $("currentSetupName");
  const $list = $("setupsList");
  const $listEmpty = $("setupsEmpty");
  const $editor = $("setupsEditor");
  const $title = $("setupsEditorTitle");
  const $name = $("setupName");
  const $car = $("setupCar");
  const $track = $("setupTrack");
  const $notes = $("setupNotes");
  const $dirty = $("setupsDirty");
  const $save = $("setupsSave");
  const $cancel = $("setupsCancel");
  const $new = $("setupsNew");
  const $strip = $("setupsStrip");
  const $sections = $("setupsSections");
  const $unitsBtns = document.querySelectorAll(".units-toggle button");

  // ---- init ----------------------------------------------------------------
  document.addEventListener("DOMContentLoaded", init);
  window.addEventListener("hashchange", onHash);
  $tabLive.addEventListener("click", () => { location.hash = ""; });
  $tabSetups.addEventListener("click", () => { location.hash = "#setups"; });
  $chip.addEventListener("click", () => { location.hash = "#setups"; });
  $new.addEventListener("click", () => loadIntoEditor({ __new: true }));
  $save.addEventListener("click", save);
  $cancel.addEventListener("click", cancel);
  $chip.classList.remove("has-setup");

  // Listen for input changes on the whole sections container (delegated).
  // Attached once at init — renderSections() re-creates the inner DOM, but
  // the listener on the stable $sections parent is reused.
  $sections.addEventListener("input", onFieldInput);

  bus.on("setup:change", (s) => {
    CURRENT_SETUP = s || null;
    CURRENT_SETUP_ID = s ? s.id : null;
    renderChip();
    renderList();
  });
  bus.on("view:change", () => { /* nothing to do here; app.js reads this */ });

  async function init() {
    try {
      SCHEMA = await fetchJSON("/api/setups/schema");
    } catch (e) {
      console.error("failed to load schema", e);
      SCHEMA = { sections: [] };
    }
    try {
      const sess = await fetchJSON("/api/session/setup");
      CURRENT_SETUP = sess.setup || null;
      CURRENT_SETUP_ID = sess.setup_id || null;
    } catch { /* no session yet */ }
    renderChip();
    await refreshList();
    // units toggle
    for (const b of $unitsBtns) b.addEventListener("click", onUnitsToggle);
    onHash();
  }

  // ---- hash routing --------------------------------------------------------
  function onHash() {
    const isSetups = location.hash === "#setups";
    $setups.hidden = !isSetups;
    $live.hidden = isSetups;
    $tabLive.setAttribute("aria-selected", String(!isSetups));
    $tabSetups.setAttribute("aria-selected", String(isSetups));
    bus.emit("view:change", isSetups ? "setups" : "live");
  }

  // ---- chip + list ---------------------------------------------------------
  function renderChip() {
    if (CURRENT_SETUP) {
      $chipName.textContent = CURRENT_SETUP.name || "(unnamed)";
      $chip.classList.add("has-setup");
      $chip.title = `Current: ${CURRENT_SETUP.name} — click to manage setups`;
    } else {
      $chipName.textContent = "no setup attached";
      $chip.classList.remove("has-setup");
      $chip.title = "Click to manage setups";
    }
  }

  function relativeTime(ts) {
    if (!ts) return "";
    const s = Math.max(0, (Date.now() / 1000) - ts);
    if (s < 60) return "just now";
    if (s < 3600) return `${Math.floor(s / 60)}m ago`;
    if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
    return `${Math.floor(s / 86400)}d ago`;
  }

  async function refreshList() {
    try {
      const out = await fetchJSON("/api/setups");
      LIST = out.setups || [];
    } catch { LIST = []; }
    renderList();
  }

  function renderList() {
    $list.innerHTML = "";
    $listEmpty.hidden = LIST.length > 0;
    for (const s of LIST) {
      const li = document.createElement("li");
      if (CURRENT_SETUP_ID === s.id) li.classList.add("current");
      li.dataset.id = s.id;
      const carTrack = [s.car, s.track].filter(Boolean).join(" · ");
      li.innerHTML = `
        <div class="row-name"></div>
        <div class="row-meta"></div>
        <div class="row-actions"></div>`;
      li.querySelector(".row-name").textContent = s.name || "(unnamed)";
      li.querySelector(".row-meta").textContent =
        `${carTrack || "—"} · updated ${relativeTime(s.updated_at)}`;
      if (CURRENT_SETUP_ID === s.id) {
        // Inline "● Current" chip inside the name row (NOT absolute-positioned
        // over the Detach button). Fixes R2-2: previous layout overlapped
        // the badge and the Detach button.
        const chip = document.createElement("span");
        chip.className = "row-current";
        chip.textContent = "● Current";
        li.querySelector(".row-name").appendChild(chip);
        const det = btn("Detach", async (e) => {
          e.stopPropagation();
          await attach(null);
        });
        li.querySelector(".row-actions").appendChild(det);
      } else {
        const at = btn("Attach", async (e) => {
          e.stopPropagation();
          await attach(s.id);
        });
        const ed = btn("Edit", (e) => {
          e.stopPropagation();
          openSetup(s.id);
        });
        const del = btn("Delete", async (e) => {
          e.stopPropagation();
          if (!confirm(`Delete "${s.name}"? This cannot be undone.`)) return;
          await deleteSetup(s.id);
        });
        const actions = li.querySelector(".row-actions");
        actions.append(at, ed, del);
      }
      li.addEventListener("click", () => openSetup(s.id));
      $list.appendChild(li);
    }
  }

  function btn(label, onClick) {
    const b = document.createElement("button");
    b.type = "button";
    b.textContent = label;
    b.addEventListener("click", onClick);
    return b;
  }

  // ---- attach / detach -----------------------------------------------------
  async function attach(setupId) {
    try {
      const out = await fetchJSON("/api/session/setup", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ setup_id: setupId }),
      });
      CURRENT_SETUP = out.setup || null;
      CURRENT_SETUP_ID = out.setup_id || null;
      bus.emit("setup:change", CURRENT_SETUP);
    } catch (e) {
      toast(`Couldn't attach: ${e.message}`);
    }
  }

  async function deleteSetup(id) {
    try {
      await fetchJSON(`/api/setups/${encodeURIComponent(id)}`, { method: "DELETE" });
      toast("Deleted");
      if (CURRENT_SETUP_ID === id) {
        CURRENT_SETUP = null;
        CURRENT_SETUP_ID = null;
        bus.emit("setup:change", null);
      }
      if (LOADED && LOADED.id === id) {
        LOADED = null; FORM = null; $editor.hidden = true;
      }
      await refreshList();
    } catch (e) {
      toast(`Couldn't delete: ${e.message}`);
    }
  }

  // ---- editor --------------------------------------------------------------
  async function openSetup(id) {
    try {
      const full = await fetchJSON(`/api/setups/${encodeURIComponent(id)}`);
      loadIntoEditor(full);
    } catch (e) {
      toast(`Couldn't open: ${e.message}`);
    }
  }

  function loadIntoEditor(setup) {
    LOADED = setup;
    FORM = setup.__new
      ? { name: "", car: "", track: "", fields: {}, notes: "", units: "english" }
      : {
          name: setup.name || "",
          car: setup.car || "",
          track: setup.track || "",
          fields: deepClone(setup.fields || {}),
          notes: setup.notes || "",
          units: setup.units || "english",
        };
    $title.textContent = setup.__new ? "New setup" : `Edit: ${setup.name || "(unnamed)"}`;
    $name.value = FORM.name;
    $car.value = FORM.car;
    $track.value = FORM.track;
    $notes.value = FORM.notes;
    syncUnitsToggle();
    $editor.hidden = false;
    renderStrip();
    renderSections();
    updateDirty();
    // scroll editor into view on narrow screens
    if (window.innerWidth <= 980) $editor.scrollIntoView({ behavior: "smooth" });
  }

  function deepClone(o) { return JSON.parse(JSON.stringify(o || {})); }

  function isDirty() {
    if (!LOADED || LOADED.__new) {
      return Boolean(FORM.name && FORM.name.trim());
    }
    return JSON.stringify(FORM) !== JSON.stringify({
      name: LOADED.name || "", car: LOADED.car || "", track: LOADED.track || "",
      fields: LOADED.fields || {}, notes: LOADED.notes || "",
      units: LOADED.units || "english",
    });
  }

  function updateDirty() {
    const d = isDirty();
    $dirty.hidden = !d;
    $save.disabled = !d;
  }

  // ---- 9-segment strip -----------------------------------------------------
  function renderStrip() {
    $strip.innerHTML = "";
    SCHEMA.sections.forEach((sec, i) => {
      const b = document.createElement("button");
      b.type = "button";
      b.title = sec.label;
      const filled = sectionFillCount(sec) === sec.fields.length && sec.fields.length > 0;
      if (filled) b.classList.add("filled");
      b.addEventListener("click", () => {
        const details = $sections.querySelectorAll("details.section-card")[i];
        if (details) {
          details.open = true;
          details.scrollIntoView({ behavior: "smooth", block: "start" });
        }
      });
      $strip.appendChild(b);
    });
  }

  function sectionFillCount(sec) {
    const f = FORM.fields[sec.key] || {};
    return sec.fields.filter(fld => f[fld.key] != null && f[fld.key] !== "").length;
  }

  // ---- sections ------------------------------------------------------------
  function renderSections() {
    $sections.innerHTML = "";
    SCHEMA.sections.forEach((sec, i) => {
      const card = document.createElement("details");
      card.className = "section-card";
      card.open = i === 0;  // first section open
      const total = sec.fields.length;
      const filled = sectionFillCount(sec);
      const sum = document.createElement("summary");
      sum.innerHTML = `
        <span><span class="chev">▸</span> ${escapeHtml(sec.label)}</span>
        <span class="fill-count ${filled === total ? "full" : ""}">${filled}/${total}</span>`;
      card.appendChild(sum);
      const body = document.createElement("div");
      body.className = "body";
      // group fields by their layout (per_axle/single/list)
      renderSectionBody(body, sec);
      card.addEventListener("toggle", () => {
        // re-render fill count when toggled (no-op for content, but cheap)
        const total = sec.fields.length;
        const filled = sectionFillCount(sec);
        sum.querySelector(".fill-count").className =
          "fill-count " + (filled === total ? "full" : "");
        sum.querySelector(".fill-count").textContent = `${filled}/${total}`;
      });
      card.appendChild(body);
      $sections.appendChild(card);
    });
  }

  function renderSectionBody(body, sec) {
    const isGears = sec.key === "gearing";
    if (isGears) {
      // special: final_drive single + gears list
      const fd = sec.fields.find(f => f.key === "final_drive");
      const gears = sec.fields.find(f => f.key === "gears");
      if (fd) body.appendChild(makeFieldRow([fd], 1));
      if (gears) {
        const list = document.createElement("div");
        list.className = "gears-list";
        const wrap = document.createElement("div");
        wrap.className = "field";
        wrap.appendChild(makeListGroup(gears, list));
        body.appendChild(wrap);
      }
      return;
    }
    // otherwise: group by group kind
    const groups = {}; // group name -> [field]
    for (const f of sec.fields) (groups[f.group] = groups[f.group] || []).push(f);
    for (const gname of Object.keys(groups)) {
      const fields = groups[gname];
      if (gname === "per_axle") {
        // pair up into Front/Rear rows by suffix
        const pairs = pairPerAxle(fields);
        for (const pair of pairs) body.appendChild(makeFieldRow(pair, 2));
      } else if (gname === "single") {
        for (const f of fields) body.appendChild(makeFieldRow([f], 1));
      } else if (gname === "list") {
        const list = document.createElement("div");
        list.className = "gears-list";
        const wrap = document.createElement("div");
        wrap.className = "field";
        wrap.appendChild(makeListGroup(fields[0], list));
        body.appendChild(wrap);
      }
    }
  }

  function pairPerAxle(fields) {
    // Pair per-axle fields into Front|Rear rows.
    // Two patterns: suffixed (camber_front/camber_rear) and bare (front/rear).
    const out = [];
    const seen = new Set();
    const partner = (key) => {
      const suff = key.match(/^(.*)_(front|rear)$/);
      if (suff) {
        const other = suff[2] === "front" ? "rear" : "front";
        return `${suff[1]}_${other}`;
      }
      if (key === "front") return "rear";
      if (key === "rear") return "front";
      return null;
    };
    for (const f of fields) {
      if (seen.has(f.key)) continue;
      const pk = partner(f.key);
      if (pk) {
        const p = fields.find(x => x.key === pk);
        out.push(p ? [f, p] : [f]);
        seen.add(f.key); if (p) seen.add(p.key);
      } else {
        out.push([f]);
        seen.add(f.key);
      }
    }
    return out;
  }

  function makeFieldRow(fields, cols) {
    const row = document.createElement("div");
    row.className = `field-row ${cols === 2 ? "two" : cols === 3 ? "three" : "four"}`;
    for (const f of fields) row.appendChild(makeField(f));
    return row;
  }

  function makeField(f) {
    const wrap = document.createElement("div");
    wrap.className = "field";
    const label = document.createElement("label");
    label.textContent = f.label;
    wrap.appendChild(label);
    const iw = document.createElement("div");
    iw.className = "field-input-wrap";
    const input = document.createElement("input");
    input.type = "number";
    input.step = "any";
    input.dataset.section = currentSectionFor(f);
    input.dataset.field = f.key;
    const sec = input.dataset.section;
    const cur = (FORM.fields[sec] || {})[f.key];
    input.value = cur == null ? "" : cur;
    iw.appendChild(input);
    if (f.unit) {
      const unit = document.createElement("span");
      unit.className = "field-unit";
      unit.textContent = unitLabelFor(f);
      iw.appendChild(unit);
    }
    wrap.appendChild(iw);
    return wrap;
  }

  function currentSectionFor(fieldMeta) {
    // find the section in schema that contains this field
    for (const sec of SCHEMA.sections) {
      if (sec.fields.some(f => f.key === fieldMeta.key)) return sec.key;
    }
    return "";
  }

  function unitLabelFor(f) {
    if (!f.unit) return "";
    if (FORM.units === "metric" && f.unit_metric) return f.unit_metric;
    if (FORM.units === "english" && f.unit_english) return f.unit_english;
    return f.unit;
  }

  function makeListGroup(f, list) {
    const sec = currentSectionFor(f);
    // Read the existing array from FORM, or fall back to an empty local.
    // Don't write back to FORM.fields during render — that would inject
    // empty arrays into FORM, spuriously marking the form as dirty.
    const existing = (FORM.fields[sec] || {})[f.key];
    let arr = Array.isArray(existing) ? existing.slice() : [];
    const writeBack = () => {
      FORM.fields[sec] = FORM.fields[sec] || {};
      if (arr.length === 0) {
        delete FORM.fields[sec][f.key];
      } else {
        FORM.fields[sec][f.key] = arr;
      }
    };
    const labels = ["1st", "2nd", "3rd", "4th", "5th", "6th", "7th", "8th", "9th", "10th"];
    const drawRows = () => {
      list.innerHTML = "";
      arr.forEach((v, idx) => {
        const row = document.createElement("div");
        row.className = "gears-row";
        const lbl = document.createElement("div");
        lbl.className = "gear-label";
        lbl.textContent = labels[idx] || `gear ${idx + 1}`;
        const iw = document.createElement("div");
        iw.className = "field-input-wrap";
        const input = document.createElement("input");
        input.type = "number";
        input.step = "any";
        input.value = v == null ? "" : v;
        input.addEventListener("input", () => {
          const x = parseFloat(input.value);
          arr[idx] = isNaN(x) ? null : x;
          writeBack();
          updateDirty(); renderStrip(); updateFillCounts();
        });
        iw.appendChild(input);
        const unit = document.createElement("span");
        unit.className = "field-unit";
        unit.textContent = f.unit || "";
        iw.appendChild(unit);
        const rm = document.createElement("button");
        rm.type = "button";
        rm.className = "gear-remove";
        rm.textContent = "×";
        rm.title = "Remove gear";
        rm.addEventListener("click", () => {
          arr.splice(idx, 1); drawRows(); writeBack();
          updateDirty(); renderStrip(); updateFillCounts();
        });
        row.append(lbl, iw, rm);
        list.appendChild(row);
      });
    };
    drawRows();
    const add = document.createElement("button");
    add.type = "button";
    add.className = "gears-add";
    add.textContent = "+ gear";
    add.addEventListener("click", () => {
      const last = arr.length ? Number(arr[arr.length - 1]) : 3.0;
      const next = isNaN(last) ? 1.0 : Math.max(0.5, last * 0.75);
      arr.push(Number(next.toFixed(3)));
      drawRows(); writeBack();
      updateDirty(); renderStrip(); updateFillCounts();
    });
    const wrap = document.createElement("div");
    wrap.append(list, add);
    return wrap;
  }

  // ---- field input handler -------------------------------------------------
  function onFieldInput(e) {
    const t = e.target;
    if (!(t instanceof HTMLInputElement)) return;
    const sec = t.dataset.section; const fk = t.dataset.field;
    if (!sec || !fk) return;
    FORM.fields[sec] = FORM.fields[sec] || {};
    const x = parseFloat(t.value);
    if (t.value === "" || isNaN(x)) {
      delete FORM.fields[sec][fk];
    } else {
      FORM.fields[sec][fk] = x;
    }
    updateDirty();
    renderStrip();
    updateFillCounts();
  }

  function updateFillCounts() {
    SCHEMA.sections.forEach((sec, i) => {
      const card = $sections.querySelectorAll("details.section-card")[i];
      if (!card) return;
      const total = sec.fields.length;
      const filled = sectionFillCount(sec);
      const fc = card.querySelector(".fill-count");
      if (fc) {
        fc.textContent = `${filled}/${total}`;
        fc.className = "fill-count " + (filled === total ? "full" : "");
      }
    });
  }

  // ---- unit toggle (immediate save for existing, in-memory for new) -------
  function syncUnitsToggle() {
    for (const b of $unitsBtns) b.setAttribute(
      "aria-pressed", String(b.dataset.units === FORM.units));
  }

  function unitFactorsForField(f) {
    // returns the english->metric factor (or null) for a field
    return f.conversion;
  }

  function convertFields(fields, from, to) {
    if (from === to) return fields;
    const out = {};
    for (const sec of SCHEMA.sections) {
      const inSec = fields[sec.key] || {};
      const outSec = {};
      for (const f of sec.fields) {
        const v = inSec[f.key];
        if (v == null) continue;
        if (f.conversion == null) { outSec[f.key] = v; continue; }
        if (from === "english" && to === "metric") outSec[f.key] = v * f.conversion;
        else if (from === "metric" && to === "english") outSec[f.key] = v / f.conversion;
        else outSec[f.key] = v;
      }
      if (Object.keys(outSec).length) out[sec.key] = outSec;
    }
    return out;
  }

  async function onUnitsToggle(e) {
    const newUnits = e.currentTarget.dataset.units;
    if (newUnits === FORM.units) return;
    const oldUnits = FORM.units;
    if (LOADED && !LOADED.__new) {
      // Existing setup: send the CURRENT (old-unit) fields together with the
      // new units. The backend is the conversion authority — it treats the
      // sent fields as being in the old unit and runs _convert_units
      // (SetupStore.update contract). We must NOT pre-convert in the
      // frontend or the conversion happens twice.
      const fieldsToSend = deepClone(FORM.fields);
      try {
        const out = await fetchJSON(`/api/setups/${encodeURIComponent(LOADED.id)}`, {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            name: FORM.name, car: FORM.car, track: FORM.track,
            fields: fieldsToSend, notes: FORM.notes, units: newUnits,
          }),
        });
        LOADED = out;
        FORM = {
          name: out.name, car: out.car, track: out.track,
          fields: deepClone(out.fields), notes: out.notes, units: out.units,
        };
        toast(`Saved in ${newUnits}`);
        syncUnitsToggle();
        await refreshList();
        renderStrip(); renderSections(); updateDirty();
      } catch (err) {
        toast(`Couldn't save units: ${err.message}`);
      }
    } else {
      // New setup: nothing exists on disk yet. Apply the conversion in-memory
      // so the displayed values match the new unit labels, and flip the
      // displayed unit. The first Save will write the converted form to disk.
      FORM.fields = convertFields(FORM.fields, oldUnits, newUnits);
      FORM.units = newUnits;
      syncUnitsToggle();
      toast(`Units: ${newUnits}`);
      renderStrip(); renderSections(); updateDirty();
    }
  }

  // ---- save / cancel -------------------------------------------------------
  async function save() {
    if (!LOADED) return;
    if (!FORM.name || !FORM.name.trim()) {
      toast("Name is required");
      $name.focus();
      return;
    }
    const payload = {
      name: FORM.name.trim(), car: FORM.car, track: FORM.track,
      fields: FORM.fields, notes: FORM.notes, units: FORM.units,
    };
    try {
      $save.disabled = true;
      let out;
      if (LOADED.__new) {
        out = await fetchJSON("/api/setups", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
      } else {
        out = await fetchJSON(`/api/setups/${encodeURIComponent(LOADED.id)}`, {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
      }
      toast("Saved");
      LOADED = out;
      FORM = {
        name: out.name, car: out.car, track: out.track,
        fields: deepClone(out.fields), notes: out.notes, units: out.units,
      };
      $title.textContent = `Edit: ${out.name}`;
      syncUnitsToggle();
      renderStrip(); renderSections(); updateDirty();
      await refreshList();
      // If the saved setup is the one currently attached to the session,
      // broadcast so the topbar chip updates (e.g. after a rename).
      if (CURRENT_SETUP_ID === out.id) {
        CURRENT_SETUP = out;
        bus.emit("setup:change", out);
      }
    } catch (e) {
      toast(`Save failed: ${e.message}`);
    } finally {
      $save.disabled = !isDirty();
    }
  }

  async function cancel() {
    if (isDirty()) {
      if (!confirm("Discard unsaved changes?")) return;
    }
    if (LOADED && LOADED.__new) {
      LOADED = null; FORM = null;
      $editor.hidden = true;
    } else if (LOADED) {
      loadIntoEditor(LOADED);  // reload from disk
    } else {
      $editor.hidden = true;
    }
  }

  // ---- meta input handlers (name/car/track/notes) --------------------------
  $name.addEventListener("input", () => { FORM.name = $name.value; updateDirty(); });
  $car.addEventListener("input", () => { FORM.car = $car.value; updateDirty(); });
  $track.addEventListener("input", () => { FORM.track = $track.value; updateDirty(); });
  $notes.addEventListener("input", () => { FORM.notes = $notes.value; updateDirty(); });

  // ---- helpers -------------------------------------------------------------
  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, c => (
      { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]
    ));
  }
  function toast(msg) {
    console.log("[setups]", msg);
    // minimal inline toast: reuse the existing insights placeholder area
    const body = $("insightsBody");
    if (!body) return;
    const prev = body.innerHTML;
    body.innerHTML = `<p class="placeholder">${escapeHtml(msg)}</p>`;
    setTimeout(() => { body.innerHTML = prev; }, 1800);
  }

  // ---- public hook (for tests / app.js) ------------------------------------
  window.__setupsView = { refreshList, attach, openSetup, getCurrent: () => CURRENT_SETUP };
})();