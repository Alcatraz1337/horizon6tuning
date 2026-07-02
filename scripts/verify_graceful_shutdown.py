"""One-off end-to-end verification: real uvicorn + live WS + graceful shutdown.

Runs uvicorn in-process, opens an idle WebSocket (server-side handler blocks on
q.get(), exactly like the reported traceback), then triggers uvicorn's graceful
shutdown. With a short `timeout_graceful_shutdown`, uvicorn cancels the parked WS
handler task -> CancelledError is injected at `await q.get()` (the reported bug).
We capture uvicorn's logs and assert no `Exception in ASGI application` is emitted.

This faithfully reproduces the user's Ctrl+C shutdown path without relying on
Windows console-signal delivery.

Run:  .venv/Scripts/python.exe scripts/verify_graceful_shutdown.py
"""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import threading
import time
import uuid

import uvicorn
import websockets

# configure before importing app so settings picks these up
os.environ["WEB_PORT"] = "0"          # unused — we configure uvicorn directly below
os.environ["UDP_PORT"] = "9971"
_LOGDIR = f"./logs_verify_{uuid.uuid4().hex[:6]}"
os.environ["LOG_DIR"] = _LOGDIR
PORT = 8771


def main() -> int:
    from app.main import create_app

    app = create_app()

    config = uvicorn.Config(
        app, host="127.0.0.1", port=PORT, log_level="info", loop="asyncio"
    )
    # short graceful timeout -> uvicorn cancels the stuck WS task after ~1.5s,
    # injecting CancelledError at the handler's `await q.get()` (the reported bug).
    config.timeout_graceful_shutdown = 1.5
    server = uvicorn.Server(config)

    # capture uvicorn + app logs
    captured: list[str] = []

    class _Capture(logging.Handler):
        def emit(self, record):
            captured.append(self.format(record))

    handler = _Capture()
    handler.setLevel(logging.INFO)
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access", "horizon6tuning"):
        logging.getLogger(name).addHandler(handler)

    # WS client in its own thread/loop: connect, hold idle (recv blocks) until
    # the server tears the connection down during shutdown.
    ws_connected = threading.Event()
    ws_done = threading.Event()

    def ws_client():
        async def hold():
            async with websockets.connect(f"ws://127.0.0.1:{PORT}/ws/telemetry") as ws:
                ws_connected.set()
                try:
                    await ws.recv()
                except websockets.ConnectionClosed:
                    pass
        try:
            asyncio.run(hold())
        finally:
            ws_done.set()

    t = threading.Thread(target=ws_client, daemon=True)
    t.start()

    # trigger shutdown shortly after the WS connects
    def trigger():
        if not ws_connected.wait(timeout=10):
            return
        time.sleep(0.5)  # ensure handler is parked on q.get()
        server.should_exit = True

    trig = threading.Thread(target=trigger, daemon=True)
    trig.start()

    # run uvicorn in the main thread (installs its signal handlers here)
    server.run()

    t.join(timeout=5)
    output = "\n".join(captured)

    print("===== CAPTURED LOGS =====")
    print(output)
    print("===== ANALYSIS =====")

    ws_error = "Exception in ASGI application" in output
    cancel_in_ws = ("app/api/routes.py" in output and "CancelledError" in output)
    lifespan_cancel = ("lifespan" in output.lower() and "CancelledError" in output)
    shutting_down = "Shutting down" in output

    print(f"'Shutting down' reached                     : {shutting_down}")
    print(f"WS 'Exception in ASGI application' present  : {ws_error}")
    print(f"CancelledError from routes.py (WS)          : {cancel_in_ws}")
    print(f"CancelledError from lifespan (upstream)     : {lifespan_cancel}")

    shutil.rmtree(_LOGDIR, ignore_errors=True)

    if not shutting_down:
        print("\nRESULT: INCONCLUSIVE — shutdown path never ran")
        return 2
    if ws_error or cancel_in_ws:
        print("\nRESULT: FAIL — WebSocket shutdown still noisy")
        return 1
    print("\nRESULT: PASS — WebSocket shutdown is clean (any lifespan noise is upstream)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())