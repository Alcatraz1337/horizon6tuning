"""asyncio UDP listener for the Forza telemetry stream.

Receives datagrams, parses them, and fans the resulting frames out to:
  * the rolling buffer (`store.buffer`)
  * the file logger (`store.logger`)
  * any registered live subscribers (the WebSocket layer registers a callback)
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Awaitable, Callable

from ..store.buffer import TelemetryBuffer
from ..store.logger import TelemetryLogger
from . import parser as telemetry_parser

log = logging.getLogger(__name__)

FrameCallback = Callable[["telemetry_parser.TelemetryFrame"], Awaitable[None] | None]


class ForzaTelemetryProtocol(asyncio.DatagramProtocol):
    """Datagram protocol: parse each packet and dispatch to buffer/logger/subs."""

    def __init__(
        self,
        buffer: TelemetryBuffer,
        logger: TelemetryLogger | None,
        on_frame: FrameCallback | None = None,
    ) -> None:
        self._buffer = buffer
        self._logger = logger
        self._on_frame = on_frame
        self.transport: asyncio.DatagramTransport | None = None
        # stats
        self.packets_received = 0
        self.packets_parsed = 0
        self.packets_dropped = 0
        self.last_packet_at_ns: float = 0.0
        self.last_error: str | None = None

    def connection_made(self, transport: asyncio.BaseTransport) -> None:  # type: ignore[override]
        self.transport = transport  # type: ignore[assignment]
        sock = transport.get_extra_info("socket")
        log.info("Telemetry listener bound on %s", sock.getsockname() if sock else "?")

    def datagram_received(self, data: bytes, addr: tuple[str, int]) -> None:
        self.packets_received += 1
        self.last_packet_at_ns = time.time_ns()
        try:
            frame = telemetry_parser.parse(data, received_at_ns=self.last_packet_at_ns)
        except Exception as exc:  # noqa: BLE001
            self.packets_dropped += 1
            self.last_error = f"{type(exc).__name__}: {exc}"
            log.warning("dropped packet (%d bytes) from %s: %s", len(data), addr, exc)
            return

        self.packets_parsed += 1
        self._buffer.append(frame)
        if self._logger is not None:
            try:
                self._logger.log(frame, index=self.packets_parsed)
            except Exception as exc:  # noqa: BLE001
                log.warning("logger failed: %s", exc)

        if self._on_frame is not None:
            res = self._on_frame(frame)
            if asyncio.iscoroutine(res):
                # fire-and-forget on the running loop
                asyncio.ensure_future(res)

    def error_received(self, exc: Exception) -> None:  # type: ignore[override]
        self.last_error = str(exc)
        log.error("UDP listener error: %s", exc)


class TelemetryServer:
    """Owns the UDP socket + protocol and exposes status + subscriber hooks."""

    def __init__(self, host: str, port: int, buffer: TelemetryBuffer,
                 logger: TelemetryLogger | None) -> None:
        self.host = host
        self.port = port
        self._buffer = buffer
        self._logger = logger
        self._protocol: ForzaTelemetryProtocol | None = None
        self._on_frame: FrameCallback | None = None

    def set_on_frame(self, cb: FrameCallback) -> None:
        self._on_frame = cb
        if self._protocol is not None:
            self._protocol._on_frame = cb

    async def start(self) -> None:
        loop = asyncio.get_running_loop()
        transport, protocol = await loop.create_datagram_endpoint(
            lambda: ForzaTelemetryProtocol(self._buffer, self._logger, self._on_frame),
            local_addr=(self.host, self.port),
            allow_broadcast=False,
        )
        self._protocol = protocol  # type: ignore[assignment]
        # keep transport ref so it isn't GC'd
        self._transport = transport

    def status(self) -> dict:
        p = self._protocol
        if p is None:
            return {"listening": False, "host": self.host, "port": self.port}
        return {
            "listening": True,
            "host": self.host,
            "port": self.port,
            "packets_received": p.packets_received,
            "packets_parsed": p.packets_parsed,
            "packets_dropped": p.packets_dropped,
            "last_packet_age_ms": max(0, (time.time_ns() - p.last_packet_at_ns) / 1e6)
            if p.last_packet_at_ns else None,
            "last_error": p.last_error,
        }