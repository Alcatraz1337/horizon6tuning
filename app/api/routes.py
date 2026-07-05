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
from ..store.setups import (
    SETUP_FIELD_SCHEMA, SETUP_FIELD_META, is_valid_setup_id,
)
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
    except WebSocketDisconnect:
        pass
    except Exception as exc:  # noqa: BLE001
        log.warning("ws error: %s", exc)
    finally:
        _manager.disconnect(ws)


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


# ---- logging control -------------------------------------------------------
# ROADMAP item 1: a top-bar toggle starts/stops the file logger without
# restarting the app. Default is off on launch; each "on" period is one
# timestamped CSV/JSONL pair on disk.

@router.get("/api/logging")
async def logging_state() -> dict:
    logger = router.state.get("logger")
    return logger.info() if logger else {"active": False}


@router.post("/api/logging")
async def logging_toggle(payload: dict | None = None) -> dict:
    logger = router.state.get("logger")
    if logger is None:
        raise HTTPException(status_code=503, detail="logger not initialized")
    enabled = (payload or {}).get("enabled")
    if not isinstance(enabled, bool):
        raise HTTPException(status_code=400, detail="body must include boolean 'enabled'")
    return logger.start() if enabled else logger.stop()


# ---- per-lap segmentation ---------------------------------------------------
# ROADMAP item 2: lap boundaries detected from the live stream; per-lap
# summaries served read-only. Lap state lives on `router.state["laps"]`.

@router.get("/api/laps")
async def laps_list() -> dict:
    laps = router.state.get("laps")
    if laps is None:
        return {"current": None, "completed": []}
    return {"current": laps.current(), "completed": laps.completed()}


@router.get("/api/laps/{lap_number}")
async def lap_detail(lap_number: int):
    laps = router.state.get("laps")
    if laps is None:
        return JSONResponse({"error": f"lap {lap_number} not found"}, status_code=404)
    out = laps.lap(lap_number)
    if out is None:
        return JSONResponse({"error": f"lap {lap_number} not found"}, status_code=404)
    return out


# ---- setup library ----------------------------------------------------------
# ROADMAP item 3: setups stored as JSON in setups/; the current live session
# can reference one setup via an in-memory id (persisted by item 5's
# sessions.json). State lives on router.state["setups"] + ["current_setup_id"].


@router.get("/api/setups")
async def setups_list() -> dict:
    store = router.state.get("setups")
    if store is None:
        return JSONResponse({"error": "setups store not initialized"}, status_code=503)
    return {"setups": store.list()}


@router.get("/api/setups/{setup_id}")
async def setup_detail(setup_id: str):
    store = router.state.get("setups")
    if store is None:
        return JSONResponse({"error": "setups store not initialized"}, status_code=503)
    out = store.get(setup_id)
    if out is None:
        return JSONResponse({"error": f"setup {setup_id} not found"}, status_code=404)
    return out


@router.post("/api/setups")
async def setup_create(payload: dict | None = None) -> dict:
    store = router.state.get("setups")
    if store is None:
        return JSONResponse({"error": "setups store not initialized"}, status_code=503)
    try:
        return store.create(payload or {})
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)


@router.put("/api/setups/{setup_id}")
async def setup_update(setup_id: str, payload: dict | None = None):
    store = router.state.get("setups")
    if store is None:
        return JSONResponse({"error": "setups store not initialized"}, status_code=503)
    try:
        out = store.update(setup_id, payload or {})
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    if out is None:
        return JSONResponse({"error": f"setup {setup_id} not found"}, status_code=404)
    return out


@router.delete("/api/setups/{setup_id}")
async def setup_delete(setup_id: str):
    store = router.state.get("setups")
    if store is None:
        return JSONResponse({"error": "setups store not initialized"}, status_code=503)
    if not store.delete(setup_id):
        return JSONResponse({"error": f"setup {setup_id} not found"}, status_code=404)
    return {"deleted": setup_id}


@router.post("/api/session/setup")
async def session_attach_setup(payload: dict | None = None) -> dict:
    store = router.state.get("setups")
    if store is None:
        return JSONResponse({"error": "setups store not initialized"}, status_code=503)
    setup_id = (payload or {}).get("setup_id")
    if setup_id is None:
        router.state["current_setup_id"] = None
        return {"setup_id": None, "setup": None}
    # Validate format BEFORE store lookup so bad format = 400, missing = 404.
    if not is_valid_setup_id(setup_id):
        return JSONResponse(
            {"error": "setup_id must be a 32-char lowercase hex string"},
            status_code=400,
        )
    out = store.get(setup_id)
    if out is None:
        return JSONResponse({"error": f"setup {setup_id} not found"}, status_code=404)
    router.state["current_setup_id"] = setup_id
    return {"setup_id": setup_id, "setup": out}


@router.get("/api/session/setup")
async def session_current_setup() -> dict:
    store = router.state.get("setups")
    setup_id = router.state.get("current_setup_id")
    if not setup_id:
        return {"setup_id": None, "setup": None}
    setup = store.get(setup_id) if store is not None else None
    return {"setup_id": setup_id, "setup": setup}


# ---- setup schema ----------------------------------------------------------
# ROADMAP item 4: the Setups editor fetches the 9-section field schema
# (label, group, unit, conversion) once on load and renders the form
# dynamically. Reads module-level constants — no store dependency, works
# even before SetupStore is initialized (no 503 path).

@router.get("/api/setups/schema")
async def setups_schema() -> dict:
    sections: list[dict] = []
    for section_key, field_keys in SETUP_FIELD_SCHEMA.items():
        fields: list[dict] = []
        for fk in field_keys:
            meta = SETUP_FIELD_META[(section_key, fk)]
            fields.append({"key": fk, **meta})
        # human-friendly section label = section_key with underscores -> spaces, titlecased
        label = section_key.replace("_", " ").title()
        sections.append({"key": section_key, "label": label, "fields": fields})
    return {"sections": sections}