# Logging on/off toggle — design

Date: 2026-07-03. Implements ROADMAP item 1.

## Goal

A top-bar switch in the dashboard that starts and stops the
`TelemetryLogger` without restarting the app. Defaults to **off** on launch so
no file is created until the user opts in. Turning it on opens a new timestamped
CSV/JSONL pair; turning it off closes the current files and does not start a
new one — every "on" period becomes exactly one session on disk.

## Current behavior (problem)

`TelemetryLogger.__init__` opens the CSV/JSONL files immediately, so a session
file is created on every app launch even if the user never opted in. There is
no API to stop or restart logging.

## Design

### `app/store/logger.py`

Split configuration from file lifecycle:

- `__init__(log_dir, stride, fmt)` stores config only. Does **not** open files.
  Sets `self.active = False`, `self._written = 0`, and leaves
  `csv_path`/`jsonl_path` as `None`.
- `start() -> dict` — opens a fresh timestamped CSV/JSONL pair, sets
  `active = True`, resets `_written = 0`, returns `info()`. If already active,
  returns `info()` unchanged (no second file).
- `stop() -> dict` — flushes and closes any open files, sets `active = False`,
  clears `csv_path`/`jsonl_path` back to `None`, returns `info()`. If already
  inactive, no-op.
- `log(frame, index)` — no-op when `not self.active`; otherwise same as today.
- `close()` — closes files (used on shutdown). Idempotent.
- `info()` — adds `"active": self.active` to the existing fields.

### `app/main.py`

- Construct `TelemetryLogger(...)` without opening files (now the default).
- On shutdown `finally`, call `logger.close()` (safe whether or not active).

### `app/api/routes.py`

- `POST /api/logging` accepting `{"enabled": bool}`:
  - `true` → `logger.start()`, `false` → `logger.stop()`. Returns `logger.info()`.
  - 400 if body missing `enabled`.
- `GET /api/logging` → `logger.info()`.
- `/api/status` already returns `logger.info()`; the new `active` field flows
  through with no further changes.

### Frontend (`index.html`, `app.js`, `styles.css`)

A top-bar toggle button next to the existing status block:

- Two visual states: "Logging off" (dim) and "Logging on" (accent).
- Click → `POST /api/logging {enabled: !current}`. Disabled briefly during the
  in-flight request.
- State is sourced from the existing 1-second `/api/status` poll
  (`s.logger.active`), so it stays in sync even if the server state changes
  for any reason. Missing `logger` (server starting) renders as off.

## Tests

`tests/test_logger_lifecycle.py`:

1. Constructing the logger creates no files in `log_dir`.
2. `start()` creates both CSV and JSONL files (when `fmt="both"`).
3. `stop()` closes files; the paths return to `None` in `info()`.
4. A second `start()` opens a new timestamped pair (different filename).
5. `log()` while inactive writes nothing; after `start()`, it writes rows.

## Out of scope

- Session index (`sessions.json`) — ROADMAP item 5.
- Per-lap segmentation — ROADMAP item 2.
- Persisting the "on/off" preference across restarts — the default is always
  off on launch; users opt in each session for now.