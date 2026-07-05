# Setups Editor — Round-2 Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the 5 defects the user found during manual browser verification of the Setups view (ROADMAP item 4 round 2).

**Architecture:** Small, targeted fixes to the existing frontend scaffold. Four of the five fixes touch `frontend/setups.js` (no backend changes). One is a 1-line CSS rule; one is a 1-line HTML copy change; one is a CSS+JS layout fix; one is a UX-state addition (OPEN_SECTIONS Set); one is a behavior change to the unit-toggle path (in-memory only, with back-conversion at Save time). A new E2E Python test pins the R2-Fix 4 contract.

**Tech Stack:** Vanilla HTML/CSS/JS in `frontend/` (no build step). Python 3.10+ FastAPI backend, pytest via `conda run -n fh6tuning ...`. All code-writing and reviewing agents use the **opus** model.

**Spec:** `docs/superpowers/specs/2026-07-05-setup-editor-design.md` §"Revisions from manual verification (round 2)"

**Spec diff coverage:** The user's manual-verification-checklist failures map to R2-Fix 1, 2, 3, 4. The "Additional findings" note (sections collapse on save/unit change) maps to R2-Fix 3. The "No setups yet…" empty-state UX concern maps to R2-Fix 5.

## Global Constraints

- **Branch:** `feature/setup-editor` (already checked out). One commit per task.
- **Run Python via conda:** `conda run -n fh6tuning ...` (NOT `.venv`).
- **Tests run via `conda run -n fh6tuning python -m pytest tests/ -q`.** All 68 existing tests must continue to pass after each task.
- **Match existing code style:** `from __future__ import annotations`, module docstrings, JSON responses with `JSONResponse({"error": ...}, status_code=...)` for non-200, `node --check` for JS files.
- **Frontend is vanilla JS, no build step, no JS test harness.** Round-2 fixes follow the same pattern as round 1: Python tests pin the contracts (R2-Fix 4's save-back-conversion), visual + commit review pin the rest.
- **All code-writing and reviewing agents use opus model.** Specified explicitly in every dispatch.
- **No new dependencies, no backend changes, no new config fields.** This is a UI-round-2 patch.

## File Structure

- **Modify `frontend/styles.css`** — add the `[hidden]` rule (R2-Fix 1); replace `.setups-list-items .badge` with a new `.row-current` inline chip style (R2-Fix 2).
- **Modify `frontend/index.html`** — change the empty-state copy (R2-Fix 5).
- **Modify `frontend/setups.js`** — R2-Fix 2 (inline `● Current` chip in renderList), R2-Fix 3 (OPEN_SECTIONS Set), R2-Fix 4 (in-memory unit toggle + back-convert at Save).
- **Modify `tests/test_setups.py`** — add `test_e2e_unit_toggle_then_save_via_http` (R2-Fix 4 contract: PUT body fields in OLD unit, units in payload is the new unit).
- **No changes** to `app/store/setups.py`, `app/api/routes.py`, `app/main.py`, `app/config.py`. R2 is purely frontend + 1 test.

---

### Task 1: R2-Fix 1 — CSS `[hidden]` beats class `display: grid`

**Files:**
- Modify: `frontend/styles.css` (append a 2-line block with a section comment)

**Interfaces:**
- Produces: a single CSS rule `[hidden] { display: none !important; }` that ensures the HTML `hidden` attribute wins over class-based `display: grid` on `.grid` and `.setups-view`.

- [ ] **Step 1: Append the rule to `frontend/styles.css`**

Open the file. At the end (after the last `}`), append a blank line and:

```css

/* ---- [hidden] attribute always wins over class display: rules ----
 * Used by #liveView and #setupsView (and the empty-state <p>). The class
 * `.grid{display:grid}` and `.setups-view{display:grid}` otherwise have
 * the same specificity as the user-agent [hidden] rule but come later in
 * the cascade, so they were silently winning and the hidden attribute
 * was being ignored (R2 manual step 1: both views visible at once).
 */
[hidden] { display: none !important; }
```

- [ ] **Step 2: Verify the rule landed**

Run: `grep -n '^\[hidden\]' frontend/styles.css`
Expected: one match showing `[hidden] { display: none !important; }`.

- [ ] **Step 3: Verify no existing rule was modified**

Run: `git diff --stat frontend/styles.css`
Expected: only additions, no removals or modifications of existing rules.

- [ ] **Step 4: Commit**

```bash
git add frontend/styles.css
git commit -m "fix(frontend): [hidden] !important so live/setups views actually hide (R2-1)"
```

---

### Task 2: R2-Fix 5 — Clearer empty-state copy in `index.html`

**Files:**
- Modify: `frontend/index.html` (1 line)

**Interfaces:**
- Produces: the empty-state `<p id="setupsEmpty">` reads: `No setups yet. Click + New setup to create your first tuning sheet.`

- [ ] **Step 1: Read the current empty-state line**

Run: `grep -n 'No setups yet' frontend/index.html`
Expected: one match. The line is roughly: `<p id="setupsEmpty" class="setups-empty" hidden>No setups yet — create your first tuning sheet.</p>`

- [ ] **Step 2: Edit the text**

Replace the text between `>` and `</p>` so the line reads exactly:

```html
        No setups yet. Click <b>+ New setup</b> to create your first tuning sheet.
```

(The `<b>` makes the button label stand out. The `<p>` keeps its `id` and `class` and the `hidden` attribute.)

- [ ] **Step 3: Verify the diff is one line**

Run: `git diff frontend/index.html | head -10`
Expected: only the empty-state text changed; no structural HTML changes.

- [ ] **Step 4: Commit**

```bash
git add frontend/index.html
git commit -m "fix(frontend): clearer empty-state copy directs user to + New setup (R2-5)"
```

---

### Task 3: R2-Fix 2 — Inline `● Current` chip instead of absolute-positioned badge

**Files:**
- Modify: `frontend/setups.js` (the `renderList` current-row branch, lines 135-144)
- Modify: `frontend/styles.css` (replace the `.setups-list-items .badge` rule; add a `.row-current` inline chip style)

**Interfaces:**
- Produces: when a row is current, `<span class="row-current">● Current</span>` is appended INSIDE the row's `.row-name` div (inline with the name), NOT as a sibling at the `<li>` level. The Detach button stays in `.row-actions` at `top: 8px; right: 8px`. The CSS rule `.setups-list-items .badge` is removed; a new `.row-current` style is added.

- [ ] **Step 1: Update the `renderList` current-row branch in `frontend/setups.js`**

Find the block that starts at `if (CURRENT_SETUP_ID === s.id) {` and ends at the matching `}`. The new version is:

```javascript
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
```

(The `else` branch is unchanged — it still appends Attach/Edit/Delete buttons to `.row-actions`.)

Also delete the original 3 lines that built the badge:
```javascript
        const badge = document.createElement("span");
        badge.className = "badge";
        badge.textContent = "● Current";
        li.appendChild(badge);
```

- [ ] **Step 2: Replace the `.badge` CSS rule and add `.row-current`**

In `frontend/styles.css`, find and delete the rule:

```css
.setups-list-items .badge{
  position:absolute;top:8px;right:8px;
  background:var(--accent);color:#fff;font-size:10px;font-weight:700;
  letter-spacing:.5px;padding:2px 6px;border-radius:4px;
}
```

Then ALSO delete the now-unused rule:

```css
.setups-list-items li.current .row-actions{opacity:1;right:54px}
```

(The `right:54px` offset was the bad-fix that tried to dodge the badge; with the chip inline, Detach sits at `right:8px` like the other action buttons.)

And the related adjustment — `li.current` no longer needs the right-shadow border effect tied to badge, but keep the border treatment:

```css
.setups-list-items li.current{
  border-color:rgba(255,59,48,.5);box-shadow:0 0 10px rgba(255,59,48,.12);
}
```

(Leave this rule as-is — it still applies.)

Now add the new `.row-current` style. Append to `frontend/styles.css` (after the `.row-name` rule):

```css

/* ---- row-current chip (R2-2: inline, not absolute) ---- */
.setups-list-items .row-current{
  display:inline-block;margin-left:8px;
  background:var(--accent);color:#fff;
  font-size:10px;font-weight:700;letter-spacing:.5px;
  padding:2px 6px;border-radius:4px;vertical-align:middle;
}
```

- [ ] **Step 3: Verify the JS and CSS changes are correct**

Run:
```bash
grep -n 'badge\|row-current' frontend/setups.js frontend/styles.css
```
Expected:
- `frontend/setups.js` references `.row-current` (in the new renderList branch).
- `frontend/styles.css` defines `.row-current` and has NO references to `.badge` (the old class).
- No rule with `right:54px` remains.

- [ ] **Step 4: Syntax check + commit**

Run: `node --check frontend/setups.js && echo "syntax OK"`

```bash
git add frontend/setups.js frontend/styles.css
git commit -m "fix(frontend): inline Current chip in row; no badge overlap (R2-2)"
```

---

### Task 4: R2-Fix 3 — Preserve `<details>` open/closed state across re-renders

**Files:**
- Modify: `frontend/setups.js` (add `OPEN_SECTIONS` module state; change `renderSections` to read/write it; reset in `loadIntoEditor`)

**Interfaces:**
- Produces:
  - `OPEN_SECTIONS: Set<string>` — module-level state. Initialized in `init()` or as a default-empty Set.
  - `renderSections()` sets `card.open = OPEN_SECTIONS.has(sec.key)` (with a fallback to first-section-open when the set is empty and the section is `sections[0]`).
  - The `<details>` `toggle` event handler adds/removes `sec.key` from `OPEN_SECTIONS`.
  - `loadIntoEditor(setup)` resets `OPEN_SECTIONS = new Set([SCHEMA.sections[0].key])` (only the first section open on a fresh load).

- [ ] **Step 1: Add the module state**

In `frontend/setups.js`, find the `// ---- module state ----` block and add a line after the existing `let FORM = null;`:

```javascript
  let OPEN_SECTIONS = new Set();   // section keys the user has expanded (persists across re-renders)
```

- [ ] **Step 2: Reset on every load**

Find the `loadIntoEditor(setup)` function. Add this line at the top of the function (right after the `LOADED = setup;` line), so every load (new OR existing) starts fresh:

```javascript
    OPEN_SECTIONS = new Set(SCHEMA.sections[0] ? [SCHEMA.sections[0].key] : []);
```

(`SCHEMA` is guaranteed loaded by the time `loadIntoEditor` is called from any UI path — `openSetup(id)` and `$new.click()` both run after `init()` resolves the schema fetch.)

- [ ] **Step 3: Use the set in `renderSections`**

Find `renderSections`. Change the `card.open` line and the `toggle` handler:

```javascript
  function renderSections() {
    $sections.innerHTML = "";
    SCHEMA.sections.forEach((sec, i) => {
      const card = document.createElement("details");
      card.className = "section-card";
      // R2-3: respect the user's previous open/closed state.
      // First-section default only applies when the set is empty (fresh load).
      if (OPEN_SECTIONS.size === 0 && i === 0) {
        card.open = true;
        OPEN_SECTIONS.add(sec.key);
      } else {
        card.open = OPEN_SECTIONS.has(sec.key);
      }
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
        // Persist the new open/closed state (R2-3).
        if (card.open) OPEN_SECTIONS.add(sec.key);
        else OPEN_SECTIONS.delete(sec.key);
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
```

- [ ] **Step 4: Syntax check + commit**

Run: `node --check frontend/setups.js && echo "syntax OK"`

```bash
git add frontend/setups.js
git commit -m "fix(frontend): preserve <details> open/closed state across re-renders (R2-3)"
```

---

### Task 5: R2-Fix 4 — Unit toggle in-memory only; back-convert at Save

**Files:**
- Modify: `frontend/setups.js` (the existing-setup branch of `onUnitsToggle`; the `save()` function adds a back-conversion block)

**Interfaces:**
- Produces:
  - `onUnitsToggle`: the `LOADED && !LOADED.__new` branch becomes the same in-memory conversion as the `else` branch. No immediate PUT. The form becomes dirty; Save is enabled.
  - `save()`: before building the PUT payload, if `FORM.units !== LOADED.units` and the setup is an existing one (not `__new`), convert `FORM.fields` back from `FORM.units` to `LOADED.units` so the wire payload satisfies the `SetupStore.update` contract (sent fields are in the OLD unit). The backend then converts OLD→new and the disk ends up with new-unit values.

- [ ] **Step 1: Update `onUnitsToggle` — both branches now in-memory only**

Find the `onUnitsToggle` function. Replace the entire body so both branches behave the same (in-memory conversion, no PUT):

```javascript
  async function onUnitsToggle(e) {
    const newUnits = e.currentTarget.dataset.units;
    if (newUnits === FORM.units) return;
    const oldUnits = FORM.units;
    // R2-4: unit toggle is now ALWAYS in-memory only. The form becomes
    // dirty; the user must click Save to persist. (Previously, the
    // existing-setup branch was immediate-PUT, which the user reported
    // as surprising — they expected the toggle to enable Save.)
    FORM.fields = convertFields(FORM.fields, oldUnits, newUnits);
    FORM.units = newUnits;
    syncUnitsToggle();
    toast(`Units: ${newUnits}`);
    renderStrip(); renderSections(); updateDirty();
  }
```

(Delete the entire old `if (LOADED && !LOADED.__new) { ... } else { ... }` structure.)

- [ ] **Step 2: Add the back-conversion block in `save()`**

Find `save()`. The new payload-building block (right after the `if (!FORM.name || ...) return;` early-out) becomes:

```javascript
  async function save() {
    if (!LOADED) return;
    if (!FORM.name || !FORM.name.trim()) {
      toast("Name is required");
      $name.focus();
      return;
    }
    // R2-4: if the user toggled units since load, FORM.fields is in the
    // new unit but the SetupStore.update contract says the wire payload
    // fields must be in the OLD (stored) unit. Back-convert before sending
    // so the backend can run its own OLD→new conversion and the disk ends
    // up in the new unit. (For __new setups, FORM.units IS the stored unit.)
    let fieldsToSend = FORM.fields;
    if (!LOADED.__new && FORM.units !== LOADED.units) {
      fieldsToSend = convertFields(FORM.fields, FORM.units, LOADED.units);
    }
    const payload = {
      name: FORM.name.trim(), car: FORM.car, track: FORM.track,
      fields: fieldsToSend, notes: FORM.notes, units: FORM.units,
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
```

The only new lines vs. the previous `save()` are the `let fieldsToSend = ...` + `if (!LOADED.__new && FORM.units !== LOADED.units) { ... }` block. The payload uses `fieldsToSend` instead of `FORM.fields` directly. Everything else (try/catch, `LOADED = out`, `FORM = ...`, the `setup:change` emit) is unchanged from the round-1 implementation.

- [ ] **Step 3: Syntax check + commit**

Run: `node --check frontend/setups.js && echo "syntax OK"`

```bash
git add frontend/setups.js
git commit -m "fix(frontend): unit toggle enables Save; back-convert at Save time (R2-4)"
```

---

### Task 6: Add E2E test pinning the R2-Fix 4 contract

**Files:**
- Modify: `tests/test_setups.py` (add `test_e2e_unit_toggle_then_save_via_http` after the existing `test_e2e_schema_and_unit_toggle_via_http`)

**Interfaces:**
- Produces: a new TestClient-based test that mirrors the frontend's R2-Fix 4 save path:
  1. Create an english setup with 32 PSI, 500 lb/in, 5 in.
  2. PUT `{units: "metric", fields: {tire_pressure: {front: 2.21}, ...}, ...}` (simulating: FORM.units says "metric" but the user wants the disk to end up in metric; per the contract, sent fields are in OLD english).
  3. Assert: returned `tire_pressure.front ≈ 32 PSI × 0.0689476 ≈ 2.21 bar`. (The backend will interpret the 2.21 as english PSI, then convert: 2.21 PSI → 0.152 bar. That's the double-conversion failure mode the new contract is supposed to prevent — so the test passes the OLD-unit fields to be the correct behavior.)
  4. **Rename this test** to better match its purpose: it pins the OLD-unit-fields contract that R2-Fix 4 relies on.

  Wait — actually, the existing `test_e2e_schema_and_unit_toggle_via_http` ALREADY pins the old-unit-fields contract. What R2-Fix 4 adds is that the FRONTEND (not just the test) honors it. The new test should pin the SAVE-AFTER-UNIT-TOGGLE behavior: user starts in english, the frontend toggles to metric (in-memory only), then Save. The Save sends the BACK-CONVERTED (old=english, values=32) payload plus `units: "metric"`. From the server's POV this is identical to the old test.

  Therefore: **the new test should EXACTLY mirror the existing E2E test, but with a comment explaining it now also covers R2-Fix 4's save-back-convert contract.** Or, since the contract was already pinned, we just need to add a new test that simulates: a user with FORM.units="metric" sends a save with the BACK-CONVERTED fields — and the disk ends up in metric. The existing test already does this.

  **Decision:** instead of adding a near-duplicate test, ADD A NEW TEST that exercises the SPECIFIC round-trip: english → toggle to metric (no save) → save with back-converted fields → verify disk is in metric. This is the R2-Fix 4 contract. It uses the same PUT body shape as the existing test, so it's really a contract-pinning test for the frontend's save-after-toggle behavior.

- [ ] **Step 1: Add the new test**

Append to `tests/test_setups.py` (after the existing `test_e2e_schema_and_unit_toggle_via_http`):

```python
def test_e2e_save_after_unit_toggle_back_converts(tmp_path) -> None:
    """R2-4 contract: the frontend's unit toggle is in-memory only; the
    user must click Save. The Save back-converts FORM.fields from the new
    unit back to the OLD (stored) unit before sending, so the wire
    payload satisfies the SetupStore.update contract ("sent fields are
    in the OLD unit"). The backend then runs its own OLD->new conversion.

    This test simulates that exact contract: the wire payload contains
    ENGLISH values (32 PSI, 500 lb/in, 5 in) but `units: "metric"`. The
    disk should end up in metric with converted values.
    """
    import os
    os.environ["SETUPS_DIR"] = str(tmp_path)
    try:
        from importlib import reload
        from app import config as _config, main as _main
        reload(_config)
        reload(_main)
        from fastapi.testclient import TestClient
        with TestClient(_main.create_app()) as c:
            r = c.post("/api/setups", json={
                "name": "r2-4", "units": "english",
                "fields": {
                    "tire_pressure": {"front": 32.0, "rear": 30.0},
                    "springs": {"spring_rate_front": 500.0, "ride_height_front": 5.0},
                },
            })
            assert r.status_code == 200
            sid = r.json()["id"]

            # Simulate: user toggles unit to metric (in-memory), then clicks
            # Save. The Save back-converts FORM.fields to the OLD (english)
            # unit, so the wire payload fields ARE in english even though
            # `units: "metric"` says the new unit.
            r = c.put(f"/api/setups/{sid}", json={
                "units": "metric",
                "fields": {
                    "tire_pressure": {"front": 32.0, "rear": 30.0},   # english PSI
                    "springs": {"spring_rate_front": 500.0, "ride_height_front": 5.0},
                },
            })
            assert r.status_code == 200
            body = r.json()
            assert body["units"] == "metric"
            # Single backend conversion: 32 PSI -> 2.21 bar
            assert abs(body["fields"]["tire_pressure"]["front"] - 32.0 * 0.0689476) < 0.01
            # File on disk reflects the conversion
            raw = json.loads((tmp_path / f"{sid}.json").read_text())
            assert raw["units"] == "metric"
            assert abs(raw["fields"]["tire_pressure"]["front"] - 32.0 * 0.0689476) < 0.01
    finally:
        os.environ.pop("SETUPS_DIR", None)
        from importlib import reload
        from app import config as _config, main as _main
        reload(_config)
        reload(_main)
```

- [ ] **Step 2: Run the new test**

Run: `conda run -n fh6tuning python -m pytest tests/test_setups.py::test_e2e_save_after_unit_toggle_back_converts -v`
Expected: PASS.

- [ ] **Step 3: Run the full suite to confirm no regression**

Run: `conda run -n fh6tuning python -m pytest tests/ -q`
Expected: 69 passed (1 new test added; the 68 existing tests still pass).

- [ ] **Step 4: Commit**

```bash
git add tests/test_setups.py
git commit -m "test(setups): pin R2-4 contract — Save back-converts fields to old unit"
```

---

### Task 7: Update ROADMAP summary note to reflect round-2

**Files:**
- Modify: `ROADMAP.md` (item 4's summary note, the `*(Implemented: ...)*` block)

**Interfaces:**
- Produces: the summary note in `ROADMAP.md` for item 4 mentions the round-2 fixes (R2-1..5) so a reader of the roadmap can see that the 5 manual-verification defects were found and fixed.

- [ ] **Step 1: Read the current summary note**

Run: `grep -n 'Implemented' ROADMAP.md`
Expected: one match around item 4 (the `*(Implemented: ...)*` block from round 1).

- [ ] **Step 2: Add a round-2 sentence to the note**

In the same `*(...)*` block, add a new sentence at the end (before the closing `)*`). The added text:

> Round 2 fixes (R2-1..R2-5) from manual verification: [hidden] CSS rule so live/setups views actually hide, inline Current chip in row (no Detach overlap), preserve details-section open/closed state across re-renders, unit toggle enables Save (in-memory only; Save back-converts fields to old unit to honor the SetupStore.update contract), clearer empty-state copy.

So the new closing text in the `*(...)*` block reads: `... Item 21 (in-app setup library: search/filter/duplicate) builds on this.)*` becomes:

```
   *(Implemented: `app/store/setups.py` `SETUP_FIELD_SCHEMA` + `SETUP_FIELD_META` +
   `Setup.units` + `_convert_units`; `GET /api/setups/schema`; `frontend/common.js`
   + `frontend/setups.js` with topbar tabs, hash routing, 9-segment strip,
   explicit Save, Metric/English toggle, attach/detach. Tests: 8 new cases in
   `tests/test_setups.py` cover schema shape, unit round-trip, file-adapts-on-disk,
   invalid-unit default, non-convertible pass-through. `tire_pressure` schema
   corrected to per-axle (was per-wheel). Spec at
   `docs/superpowers/specs/2026-07-05-setup-editor-design.md`. Not yet merged to
   `main`. Item 21 (in-app setup library: search/filter/duplicate) builds on
   this. **Round 2** (R2-1..R2-5, manual-verification fixes): `[hidden]` CSS
   rule so live/setups views actually hide; inline Current chip in row (no
   Detach overlap); preserve details-section open/closed state across
   re-renders; unit toggle enables Save (in-memory only; Save back-converts
   fields to old unit to honor the SetupStore.update contract); clearer
   empty-state copy. New E2E test pins the R2-4 back-conversion contract.)*
```

- [ ] **Step 3: Verify only the one block changed**

Run: `git diff ROADMAP.md`
Expected: the only change is the appended "Round 2" sentence inside the existing `*(...)*` block.

- [ ] **Step 4: Commit**

```bash
git add ROADMAP.md
git commit -m "docs(roadmap): note round-2 fixes (R2-1..R2-5) in item 4 summary"
```

---

### Task 8: Final whole-branch review (round 2)

**Files:** none.

**Steps:**

- [ ] **Step 1: Run the full Python test suite**

Run: `conda run -n fh6tuning python -m pytest tests/ -q`
Expected: 69 passed.

- [ ] **Step 2: Run the JS syntax check**

Run: `node --check frontend/common.js && node --check frontend/app.js && node --check frontend/setups.js && echo "all JS syntax OK"`
Expected: clean.

- [ ] **Step 3: Visual smoke test (the user runs in a browser)**

The user opens `http://127.0.0.1:8000` with the app running and walks through:
- Click Setups tab → only Setups view visible (R2-1).
- Click `+ New setup` → editor opens, all 9 sections visible, first open.
- Empty-state text reads: "No setups yet. Click **+ New setup** to create your first tuning sheet." (R2-5).
- Open sections 3 and 5. Edit a field. Click Save → sections 3 and 5 stay open (R2-3).
- Open a saved setup. Click Metric toggle → values convert in-memory; Save button enables; Save writes the converted values to disk (R2-4).
- Attach a setup → row shows `● Current` chip inline with the name; Detach button at the right, no overlap; click Detach (R2-2).
- Resize ≤980px → list/editor swap. Direct-load `#setups` → Setups view at page load.

If any step fails, file the issue and fix it before merge.

- [ ] **Step 4: Note "round-2 visual verified" in the progress ledger**

Open `.superpowers/sdd/progress.md` and append a final block summarizing the round-2 results.

---

## Final verification

After Task 8, confirm the branch is in a good state:

```bash
conda run -n fh6tuning python -m pytest tests/ -q
git status
git log --oneline main..HEAD
node --check frontend/common.js && node --check frontend/app.js && node --check frontend/setups.js && echo "all JS OK"
```

Expected: 69/69 tests pass, working tree clean, ~22 commits on `feature/setup-editor` ahead of `main`, JS syntax clean.

## Self-Review (run before execution)

- **Spec coverage:** R2-1 (CSS) → Task 1. R2-5 (HTML copy) → Task 2. R2-2 (JS renderList + CSS) → Task 3. R2-3 (JS state + renderSections) → Task 4. R2-4 (JS onUnitsToggle + save + test) → Tasks 5 and 6. ROADMAP note update → Task 7. Visual + final review → Task 8.
- **Placeholder scan:** no TBD/TODO. All code blocks are real. No "similar to Task N" without code.
- **Type consistency:**
  - `OPEN_SECTIONS` is a `Set<string>` everywhere; `add`/`delete`/`has`/`size` are used correctly.
  - `convertFields` signature unchanged (`(fields, from, to) -> dict`); used in both `onUnitsToggle` and `save()`.
  - `loadIntoEditor(setup)` signature unchanged; the `OPEN_SECTIONS` reset is added at the top.
  - `save()` signature unchanged; the new `fieldsToSend` local does NOT change the outer interface.
  - The new E2E test uses the same `os.environ["SETUPS_DIR"]` + `reload` + `try/finally` pattern as the existing one (no new helper).
- **Known wrinkles:**
  - Task 4's `renderSections` change uses `OPEN_SECTIONS.size === 0` to detect the "fresh load" case. If a user manually collapses all 9 sections and then triggers a re-render, the set will be empty and section 0 will auto-reopen. This is acceptable UX (a fully-closed form is rare; auto-reopening the first section is a sensible default). Documented in the comment in the code.
  - Task 5's `save()` back-converts only when `!LOADED.__new && FORM.units !== LOADED.units`. For a `__new` setup, `FORM.units` is the only unit; no back-conversion needed (and the new-setup fields ARE in their declared unit). For an existing setup that the user didn't toggle, `FORM.units === LOADED.units`, no back-conversion, normal save.
  - The E2E test in Task 6 mirrors the existing `test_e2e_schema_and_unit_toggle_via_http` almost exactly. This is intentional — both tests pin the same contract (wire payload fields in OLD unit), and having two tests with slightly different framing makes it clear the contract matters for both the old immediate-toggle path AND the new save-after-toggle path.
