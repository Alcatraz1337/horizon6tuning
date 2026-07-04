"""Application entrypoint: wires telemetry + storage + LLM + FastAPI together.

Run with:  python -m app.main
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from .api.routes import get_manager, router
from .config import get_settings
from .insights.service import InsightsService
from .llm.factory import build_llm_client, LLMConfigError
from .store.buffer import TelemetryBuffer
from .store.laps import LapTracker
from .store.logger import TelemetryLogger
from .store.setups import SetupStore
from .telemetry.listener import TelemetryServer

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("horizon6tuning")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()

    buffer = TelemetryBuffer(maxlen=settings.buffer_frames)
    laps = LapTracker(maxlen=200)
    logger = TelemetryLogger(
        log_dir=settings.log_dir, stride=settings.log_stride, fmt=settings.log_format
    )
    setups = SetupStore(setups_dir=settings.setups_dir)

    telemetry = TelemetryServer(
        host=settings.udp_host, port=settings.udp_port, buffer=buffer, logger=logger
    )

    # LLM client is optional at startup — dashboard works without it until a key is set.
    llm = None
    try:
        llm = build_llm_client(settings)
        log.info("LLM provider: %s (model=%s)", llm.provider, llm.model)
    except (LLMConfigError, ValueError) as exc:
        log.warning("LLM not configured at startup: %s — /api/insights will 400 until fixed", exc)

    insights = InsightsService(buffer=buffer, llm=llm)

    # wire the live WebSocket publisher and lap tracker into the UDP listener
    manager = get_manager()
    telemetry.set_on_frame(lambda frame: (manager.publish(frame), laps.on_frame(frame)))

    await telemetry.start()

    # share state with the router (APIRouter is a plain object; we attach a dict)
    router.state = {
        "telemetry_server": telemetry,
        "insights": insights,
        "buffer": buffer,
        "laps": laps,
        "logger": logger,
        "settings": settings,
        "setups": setups,
        "current_setup_id": None,
    }

    log.info("Dashboard: http://%s:%d", settings.web_host, settings.web_port)
    log.info("Listening for Forza telemetry on udp://%s:%d", settings.udp_host, settings.udp_port)

    try:
        yield
    finally:
        logger.close()
        log.info("shut down")


def create_app() -> FastAPI:
    app = FastAPI(title="horizon6tuning", version="0.1.0", lifespan=lifespan)
    app.include_router(router)

    frontend_dir = Path(__file__).resolve().parent.parent / "frontend"
    if frontend_dir.exists():
        app.mount("/static", StaticFiles(directory=str(frontend_dir)), name="static")
    return app


app = create_app()


def main() -> None:
    settings = get_settings()
    uvicorn.run(
        "app.main:app",
        host=settings.web_host,
        port=settings.web_port,
        reload=False,
        log_level="info",
    )


if __name__ == "__main__":
    main()