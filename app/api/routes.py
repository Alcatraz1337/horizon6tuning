"""HTTP + WebSocket routes.

The WebSocket broadcasts each parsed frame to connected dashboards. Subscribing
is done by registering an `on_frame` callback on the telemetry server; the
callback pushes the frame into each connection's asyncio queue so a slow client
can't block the UDP listener.
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse

from ..insights.service import InsightsService
from ..telemetry.frame import TelemetryFrame
from ..telemetry.listener import TelemetryServer

log = logging.getLogger(__name__)
router = APIRouter()

FRONTEND_DIR = Path(__file__).resolve().parent.parent.parent / "frontend"


# ---- connection manager ----------------------------------------------------

class _ConnectionManager:
    def __init__(self) -> None:
        self._active: set[WebSocket] = set()
        self._queues: dict[WebSocket, asyncio.Queue] = {}

    async def connect(self, ws: WebSocket) -> asyncio.Queue:
        await ws.accept()
        q: asyncio.Queue = asyncio.Queue(maxsize=256)
        self._active.add(ws)
        self._queues[ws] = q
        return q

    def disconnect(self, ws: WebSocket) -> None:
        self._active.discard(ws)
        self._queues.pop(ws, None)

    def publish(self, frame: TelemetryFrame) -> None:
        """Synchronous callback from the UDP listener. Drops if a queue is full."""
        for ws, q in list(self._queues.items()):
            try:
                q.put_nowait(frame)
            except asyncio.QueueFull:
                # drop oldest then insert to keep the stream fresh
                try:
                    q.get_nowait()
                    q.put_nowait(frame)
                except Exception:
                    pass


_manager = _ConnectionManager()


def get_manager() -> _ConnectionManager:
    return _manager


# ---- routes ----------------------------------------------------------------

@router.get("/")
async def index() -> FileResponse:
    path = FRONTEND_DIR / "index.html"
    if not path.exists():
        return JSONResponse({"error": "frontend/index.html not found"}, status_code=500)
    return FileResponse(path)


@router.get("/api/status")
async def status() -> dict:
    server: TelemetryServer = router.state["telemetry_server"]
    logger = router.state.get("logger")
    buf = router.state["buffer"]
    info = server.status()
    info["buffer_frames"] = len(buf)
    info["logger"] = logger.info() if logger else None
    return info


@router.websocket("/ws/telemetry")
async def telemetry_ws(ws: WebSocket) -> None:
    q = await _manager.connect(ws)
    try:
        while True:
            frame = await q.get()
            await ws.send_text(json.dumps(frame.to_dict()))
    except (WebSocketDisconnect, asyncio.CancelledError):
        # WebSocketDisconnect -> client closed the connection.
        # CancelledError   -> uvicorn cancelled this task during shutdown.
        #   asyncio.CancelledError is a BaseException (not Exception) since
        #   Python 3.8, so `except Exception` does NOT catch it. If it propagates
        #   out, uvicorn's run_asgi logs `ERROR: Exception in ASGI application`
        #   (its `except BaseException` clause). Catch it here and exit cleanly
        #   so shutdown stays quiet. This is a leaf handler at process teardown,
        #   not a structured-concurrency primitive, so swallowing is safe here.
        pass
    except Exception as exc:  # noqa: BLE001
        log.warning("ws error: %s", exc)
    finally:
        _manager.disconnect(ws)
        # best-effort close; the transport is torn down by uvicorn regardless.
        try:
            await ws.close()
        except Exception:  # noqa: BLE001
            pass


@router.post("/api/insights")
async def analyze(payload: dict | None = None) -> dict:
    service: InsightsService = router.state["insights"]
    extra = (payload or {}).get("extra")
    try:
        return service.analyze(extra=extra)
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:  # noqa: BLE001
        log.exception("insights failure")
        raise HTTPException(status_code=500, detail=f"{type(exc).__name__}: {exc}")


@router.get("/api/insights")
async def latest_insight() -> dict:
    service: InsightsService = router.state["insights"]
    out = service.latest()
    return out if out is not None else {"text": None}