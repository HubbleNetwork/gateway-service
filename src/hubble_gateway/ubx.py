"""Async UBX NAV-PVT reader for u-blox receivers (ZED-F9P, NEO-M9N, etc.)."""

from __future__ import annotations

import asyncio
import struct
from dataclasses import dataclass

import structlog

logger = structlog.get_logger(__name__)

UBX_SYNC_1 = 0xB5
UBX_SYNC_2 = 0x62
NAV_CLASS = 0x01
NAV_PVT_ID = 0x07
NAV_PVT_PAYLOAD_LEN = 92
READ_PVT_TIMEOUT_S = 10.0


def _ubx_checksum(data: bytes) -> tuple[int, int]:
    ck_a = 0
    ck_b = 0
    for byte in data:
        ck_a = (ck_a + byte) & 0xFF
        ck_b = (ck_b + ck_a) & 0xFF
    return ck_a, ck_b


def _ubx_frame(msg_class: int, msg_id: int, payload: bytes) -> bytes:
    header = struct.pack("<BBH", msg_class, msg_id, len(payload))
    body = header + payload
    ck_a, ck_b = _ubx_checksum(body)
    return b"\xb5\x62" + body + bytes([ck_a, ck_b])


NAV_PVT_POLL = _ubx_frame(NAV_CLASS, NAV_PVT_ID, b"")


@dataclass(slots=True)
class UBXNavPVT:
    itow_ms: int
    year: int
    month: int
    day: int
    hour: int
    minute: int
    second: int
    valid: int
    valid_date: bool
    valid_time: bool
    fix_type: int
    flags: int
    gnss_fix_ok: bool
    num_sv: int
    lat: float
    lon: float
    height_ellipsoid_m: float
    alt_msl_m: float
    hacc_m: float
    vacc_m: float
    ground_speed_ms: float
    heading_deg: float
    pdop: float


def _parse_nav_pvt_payload(payload: bytes) -> UBXNavPVT:
    if len(payload) != NAV_PVT_PAYLOAD_LEN:
        raise ValueError(f"NAV-PVT payload length {len(payload)}, expected {NAV_PVT_PAYLOAD_LEN}")

    itow_ms = struct.unpack_from("<I", payload, 0)[0]
    year = struct.unpack_from("<H", payload, 4)[0]
    month, day, hour, minute, second, valid = struct.unpack_from("<BBBBBB", payload, 6)
    fix_type = payload[20]
    flags = payload[21]
    num_sv = payload[23]
    lon_i, lat_i, height_mm, hmsl_mm = struct.unpack_from("<iiii", payload, 24)
    hacc_mm, vacc_mm = struct.unpack_from("<II", payload, 40)
    g_speed_mm_s, head_mot = struct.unpack_from("<ii", payload, 60)
    pdop_raw = struct.unpack_from("<H", payload, 76)[0]

    return UBXNavPVT(
        itow_ms=itow_ms, year=year, month=month, day=day,
        hour=hour, minute=minute, second=second, valid=valid,
        valid_date=bool(valid & 0x01), valid_time=bool(valid & 0x02),
        fix_type=fix_type, flags=flags, gnss_fix_ok=bool(flags & 0x01),
        num_sv=num_sv,
        lat=lat_i / 1e7, lon=lon_i / 1e7,
        height_ellipsoid_m=height_mm / 1000.0, alt_msl_m=hmsl_mm / 1000.0,
        hacc_m=hacc_mm / 1000.0, vacc_m=vacc_mm / 1000.0,
        ground_speed_ms=g_speed_mm_s / 1000.0, heading_deg=head_mot / 1e5,
        pdop=pdop_raw / 100.0,
    )


class UBXReader:
    """Async UBX reader that polls NAV-PVT from a serial port."""

    def __init__(self, port: str, baud_rate: int = 38400) -> None:
        self._port = port
        self._baud_rate = baud_rate
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._buf = bytearray()

    async def start(self) -> None:
        import serial_asyncio

        self._reader, self._writer = await serial_asyncio.open_serial_connection(
            url=self._port, baudrate=self._baud_rate,
        )
        self._buf.clear()
        logger.info("UBX reader connected", port=self._port, baud_rate=self._baud_rate)
        await self._configure_uart()

    async def _configure_uart(self) -> None:
        """Enable UBX NAV-PVT output on UART (persisted to flash)."""
        if self._writer is None:
            return
        kv = struct.pack("<IB", 0x10750001, 1)   # CFG-UART2OUTPROT-UBX = true
        kv += struct.pack("<IB", 0x20910008, 1)  # CFG-MSGOUT-UBX_NAV_PVT_UART2 = 1
        payload = struct.pack("<BBH", 0x00, 0x07, 0x0000) + kv
        frame = _ubx_frame(0x06, 0x8A, payload)
        self._writer.write(frame)
        await self._writer.drain()
        await asyncio.sleep(0.2)
        logger.info("UBX UART configured")

    def _poll_pvt(self) -> None:
        if self._writer is not None:
            self._writer.write(NAV_PVT_POLL)

    async def read_pvt(self) -> UBXNavPVT | None:
        if self._reader is None:
            raise RuntimeError("call start() first")

        self._poll_pvt()
        loop = asyncio.get_running_loop()
        deadline = loop.time() + READ_PVT_TIMEOUT_S

        while True:
            remaining = deadline - loop.time()
            if remaining <= 0:
                return None

            while len(self._buf) < 2:
                chunk = await self._read_chunk(4096, remaining)
                if not chunk:
                    return None
                self._buf.extend(chunk)
                remaining = deadline - loop.time()
                if remaining <= 0:
                    return None

            sync_at = self._buf.find(bytes([UBX_SYNC_1, UBX_SYNC_2]))
            if sync_at < 0:
                if len(self._buf) > 1:
                    del self._buf[:-1]
                elif len(self._buf) == 1 and self._buf[0] != UBX_SYNC_1:
                    self._buf.clear()
                continue

            if sync_at > 0:
                del self._buf[:sync_at]

            need = 6
            while len(self._buf) < need:
                chunk = await self._read_chunk(need - len(self._buf), remaining)
                if not chunk:
                    return None
                self._buf.extend(chunk)
                remaining = deadline - loop.time()
                if remaining <= 0:
                    return None

            payload_len = struct.unpack_from("<H", self._buf, 4)[0]
            frame_len = 6 + payload_len + 2

            while len(self._buf) < frame_len:
                chunk = await self._read_chunk(frame_len - len(self._buf), remaining)
                if not chunk:
                    return None
                self._buf.extend(chunk)
                remaining = deadline - loop.time()
                if remaining <= 0:
                    return None

            body = bytes(self._buf[2:6 + payload_len])
            ck_a, ck_b = self._buf[6 + payload_len], self._buf[6 + payload_len + 1]
            exp_a, exp_b = _ubx_checksum(body)

            if ck_a != exp_a or ck_b != exp_b:
                del self._buf[0]
                continue

            del self._buf[:frame_len]

            msg_class = body[0]
            msg_id = body[1]
            if (
                msg_class == NAV_CLASS
                and msg_id == NAV_PVT_ID
                and payload_len == NAV_PVT_PAYLOAD_LEN
            ):
                try:
                    return _parse_nav_pvt_payload(body[4:])
                except ValueError:
                    return None

    async def _read_chunk(self, max_bytes: int, timeout_s: float) -> bytes | None:
        if self._reader is None:
            return None
        try:
            return await asyncio.wait_for(
                self._reader.read(max(max_bytes, 1)), timeout=timeout_s
            )
        except asyncio.TimeoutError:
            return None

    async def stop(self) -> None:
        if self._writer is not None:
            self._writer.close()
            try:
                await self._writer.wait_closed()
            except Exception:
                pass
            self._writer = None
        self._reader = None
        self._buf.clear()
        logger.info("UBX reader stopped", port=self._port)
