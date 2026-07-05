# ROADMAP

A flat, execution-ordered list of what we are going to build for
**horizon6tuning** — a local tuning tool for Forza Horizon 6, useful from
beginner to pro, and shareable as an open-source project.

The list is intentionally flat (no phases, no "Now/Next/Later" bands). Items
are numbered in the order we plan to tackle them. We work top-down, not in
parallel. Items can be reordered as priorities shift.

### Status markers

Append a status marker to the end of an item's title line (do **not**
renumber items). Update it when state changes:

- `[done · merged]` — implemented, reviewed, and merged into `main`.
- `[done · branch <name>]` — implemented and reviewed on the named branch,
  not yet merged into `main` (PR pending or in review).
- `[in progress]` — actively being worked on.
- (no marker) — not started.

A design spec for a completed item lives in
`docs/superpowers/specs/YYYY-MM-DD-<topic>-design.md` and is committed on the
same branch as the implementation.

## How to add a new item

- Append it at the end of the list and give it the next number.
- Do **not** renumber existing items — external links and discussions will
  break.
- Use the form `N. **<Title>** — <one-sentence description of the outcome>.`
- If the item depends on a prior item, mention it explicitly
  ("depends on 5.").
- If the item is a long-term idea and not near-term work, prefix it with
  `[parked]` and put it in the "Parked ideas" section at the bottom.

## The list

1. **Logging on/off toggle** `[done · merged]` — a top-bar switch in the dashboard that starts
   and stops the `TelemetryLogger` without restarting the app. Defaults to
   *off* on launch so no file is created until the user opts in. Turning it
   on opens a new timestamped CSV/JSONL pair; turning it off closes the
   current files and does not start a new one — every "on" period becomes
   exactly one session on disk, which keeps the session index clean.
   *(Merged to `main` via PR #1, commit d992c15.)*
2. **Per-lap segmentation** `[done · branch feature/per-lap-segmentation]` — detect lap boundaries from the live stream
   (`lap_number` changes, `current_lap` resets, `distance_traveled` rollover)
   and compute per-lap summaries alongside the rolling buffer. This is the
   foundation for every later analysis feature.
   *(Implemented: `app/store/laps.py` `LapTracker` + `GET /api/laps`,
   `GET /api/laps/{n}`, wired in `main.py` lifespan; `tests/test_laps.py`
   covers all 8 spec cases. Reviewed APPROVE-WITH-NITS, nits applied, all
   tests green. Spec at
   `docs/superpowers/specs/2026-07-04-per-lap-segmentation-design.md`.
   v1 is backend + API + tests only — no frontend UI, no disk persistence
   (those are items 5/7/10). Not yet merged to `main`.)*
3. **Setup data model** `[done · branch feature/setup-data-model]` — define a `Setup` as
   `{id, name, car, track, fields: {…}, notes, created_at}` and store setups
   as JSON files in `setups/`. The 9 field sections are listed in step 4.
   A session references one setup.
4. **Setup editor (v1, all 9 categories)** — a single page in the dashboard
   with 9 collapsible sections the user fills in (FH6-verified field shapes;
   the canonical field list lives in `app/store/setups.py::SETUP_FIELD_SCHEMA`):
   - **Tire pressure** — cold pressure FL/FR/RL/RR (PSI, per-wheel)
   - **Gearing** — final drive, individual gear ratios (1st..top, list)
   - **Alignment** — camber front/rear, toe front/rear, caster (single)
   - **Anti-roll bars** — ARB front, ARB rear (stiffness)
   - **Springs** — spring rate front/rear, ride height front/rear
   - **Damping** — rebound front/rear, bump front/rear (FH6 labels
     compression "bump")
   - **Aero** — front downforce, rear downforce
   - **Brake** — brake bias, brake pressure (pad compound / rotor size are
     upgrade parts, not tuning sliders)
   - **Differential** — accel lock front/rear, decel lock front/rear,
     center balance (AWD only; FH6 has no diff preload)
   Attach a setup to the current session so the LLM knows the *current* setup
   when it generates insight.
5. **Session index + simple session browser** — maintain a `sessions.json`
   index (alongside the existing CSV/JSONL logs) listing each session with
   `{id, started_at, car, track, setup_id, best_lap, lap_count, log_paths}`.
   Add a "Past sessions" page in the dashboard listing sessions with
   best-lap, car, track, date, and a button to open one.
6. **Open past session** — clicking a session in the browser loads its
   CSV/JSONL into a read-only viewer. This is the "session is shareable /
   reviewable" primitive; lap comparison and trace view build on it.
7. **Trace view (Advanced mode)** — timeline charts for speed / RPM /
   throttle / brake / steer / gear across a single lap or selected window,
   with scrubbing. Reuse Chart.js. Lives under the Advanced mode by default.
8. **Simple / Advanced mode toggle** — top-bar switch in the dashboard.
   **Simple** = opinionated summary cards with friendly copy and a small
   fixed widget set; **Advanced** = full grid with trace view, all 84 raw
   fields, lap browser, comparison tools. The mode persists per-user
   (localStorage for v1; per-user account later if needed). [depends on 7]
9. **Per-widget expand + tooltip (layered on top of the toggle)** — every
   widget in Advanced mode gets a "?" tooltip with a plain-language
   explanation and an "expand" affordance for the underlying chart or raw
   values. Simple mode is a curated subset, not a different code path. We
   discuss each widget's expansion shape as we build it.
10. **Lap comparison view** — overlay two laps' traces and show a delta-time
    chart underneath. The first "pro" feature that actually justifies the
    Advanced mode. [depends on 7]
11. **LLM: per-lap analysis mode** — extend `POST /api/insights` to accept a
    `{mode: "live" | "lap", lap_id?: ...}` payload. Lap mode feeds the LLM
    the attached *setup* + that lap's per-lap summary + a sample of trace
    points, and asks for setup-aware tuning recommendations, not just
    driving coaching. [depends on 3, 4]
12. **LLM: structured output (setup deltas)** — move the LLM response from
    free text to a structured payload
    `{summary, issues: [{area, finding, suggested_change, confidence}], ...}`
    so the UI can render a side-by-side "current vs. suggested" view of
    setup fields. The free-text explanation remains as a fallback.
    [depends on 11]
13. **Setup comparison view** — pick two setups (current vs. previous /
    community), see the field diff, and overlay the laps run on each so the
    driver can judge whether the change actually helped. [depends on 4, 10]
14. **Sector analysis** — derive sector boundaries from position data
    (heuristic, since FH6 doesn't expose sector markers) and compute
    per-sector best times. Show in the trace view as colored bands. Useful
    for pinpointing which part of a corner to work on.
15. **Tire analytics** — per-tire temperature and slip statistics over a
    lap / stint. Detect cold/overheating tires, asymmetric setups
    (left vs. right imbalance), and tread-wear patterns. [depends on 2]
16. **Stint analytics** — fuel usage per lap, lap-time consistency (std
    dev / best 3-lap average), tire-deg trends across a stint. Surfaces in
    the insights panel for endurance races.
17. **Onboarding & first-run experience** — first-run wizard: pick your
    experience level (beginner / intermediate / pro), pick a sample car &
    track, run a 2-lap demo with synthetic telemetry, see a sample insight.
    Sets the Simple/Advanced mode default per user. [depends on 8]
18. **Beginner-friendly explanations everywhere** — every metric in the UI
    has a beginner-mode tooltip ("slip ratio = how much the tire is sliding
    vs. rolling; lower is more grip, but a tiny bit of slip at corner exit
    is faster"). Written once, reused across Simple/Advanced.
19. **Packaging & shareability** — verified clean `pip install -r
    requirements.txt` from a fresh clone; one-line `python -m app.main`
    run; cross-platform note (Windows primary, Mac/Linux best-effort);
    screenshots and a short demo GIF in the README; a `CONTRIBUTING.md`;
    GitHub Actions CI running `pytest` and the parser round-trip on push.
20. **Settings page** — `.env` is replaced in-app by a settings panel that
    writes back to `.env`: UDP host/port, LLM provider + key + model +
    base URL, log dir/stride/format, buffer size, default mode. Keeps the
    `.env` fallback for headless/server use. [depends on 19]
21. **In-app setup library** — a "My Setups" page listing all saved setups
    with search/filter by car and track, duplicate-as-template, soft-delete.
    The v1 of "I want to iterate on a tune without losing the old one."

## Parked ideas

- `[parked]` SQLite integration — keep raw CSV/JSONL exports but also
  write to a local SQLite DB (`sessions.db`) with tables for `sessions`,
  `laps`, `frames`, `setups`, `insights`. Speeds up queries and unlocks
  "show me my last 20 laps at Fuji in the R32." Revisit when in-app
  queries start to matter.
- `[parked]` Multi-sim support — generalize the parser and insight model
  beyond FH6 (Assetto Corsa, iRacing, Gran Turismo). Requires abstracting
  the wire format behind a `TelemetrySource` interface.
- `[parked]` Community setup sharing — export/import a setup as a small
  JSON file or a shareable link, with a static "setup card" image.
- `[parked]` Account + cloud sync — optional account for cross-device
  session/setup/insight history. Requires backend hosting; defer until
  local-only is solid.
- `[parked]` Mobile companion — read-only mobile view of the live
  dashboard over the local network.
- `[packaged]` Desktop installer — packaged app (PyInstaller / Tauri) for
  non-technical users. Revisit after the settings + onboarding are solid.
