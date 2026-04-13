"""Packet sender: batches, deduplicates, and uploads BLE sightings."""

import asyncio
import time
import uuid as uuid_mod
from collections.abc import Awaitable, Callable
from typing import Any

import structlog

from hubble_gateway.auth import GatewayAuth
from hubble_gateway.models import BLEPacket, Location

logger = structlog.get_logger(__name__)


class _DedupEntry:
    __slots__ = ("packet", "strongest_rssi", "sighting_count", "first_seen_ms")

    def __init__(self, packet: BLEPacket) -> None:
        self.packet = packet
        self.strongest_rssi = packet.rssi
        self.sighting_count = 1
        self.first_seen_ms = int(packet.timestamp.timestamp() * 1000)

    def merge(self, packet: BLEPacket) -> None:
        self.sighting_count += 1
        if packet.rssi > self.strongest_rssi:
            self.strongest_rssi = packet.rssi
            self.packet = packet


class GatewaySender:
    """Batches and uploads BLE sightings to the gateway API."""

    def __init__(
        self,
        auth: GatewayAuth,
        get_location: Callable[[], Awaitable[Location]] | None = None,
        batch_size: int = 500,
        upload_interval_s: float = 5.0,
        dedup_window_s: float = 300.0,
    ) -> None:
        self._auth = auth
        self._get_location = get_location
        self._batch_size = batch_size
        self._upload_interval = upload_interval_s
        self._dedup_window = dedup_window_s
        self._dedup_map: dict[tuple[str, str | None, str], _DedupEntry] = {}
        self._dedup_lock = asyncio.Lock()
        self._running = False
        self._stats_sends = 0
        self._stats_total = 0
        self._stats_uploaded = 0
        self._stats_devices: set[str] = set()

    async def start(self) -> None:
        self._running = True
        self._apply_server_config()
        asyncio.create_task(self._upload_loop())
        if self._get_location:
            asyncio.create_task(self._location_loop())
        logger.info(
            "Sender started",
            gateway_id=self._auth.gateway_id,
            upload_interval=self._upload_interval,
            dedup_window=self._dedup_window,
            batch_size=self._batch_size,
        )

    async def stop(self) -> None:
        self._running = False
        await self._flush()
        logger.info(
            "Sender stopped",
            total_packets=self._stats_total,
            uploaded=self._stats_uploaded,
            sends=self._stats_sends,
            unique_devices=len(self._stats_devices),
        )

    def add_packet(self, packet: BLEPacket) -> None:
        self._stats_total += 1
        self._stats_devices.add(packet.device_address)
        key = (packet.device_address, packet.service_uuid_16bit, packet.service_data_hex)
        existing = self._dedup_map.get(key)
        if existing is not None:
            age_ms = int(packet.timestamp.timestamp() * 1000) - existing.first_seen_ms
            if age_ms < self._dedup_window * 1000:
                existing.merge(packet)
                return
        self._dedup_map[key] = _DedupEntry(packet)

    @property
    def stats(self) -> dict[str, int]:
        return {
            "total_packets": self._stats_total,
            "uploaded_packets": self._stats_uploaded,
            "sends": self._stats_sends,
            "unique_devices": len(self._stats_devices),
            "buffer_size": len(self._dedup_map),
        }

    async def _upload_loop(self) -> None:
        while self._running:
            await asyncio.sleep(self._upload_interval)
            if not self._dedup_map:
                continue
            await self._flush()

    async def _location_loop(self) -> None:
        _INTERVAL = 60.0
        while self._running:
            await asyncio.sleep(_INTERVAL)
            if not self._get_location:
                continue
            try:
                location = await self._get_location()
                if location.latitude is not None and location.longitude is not None:
                    await self._upload_location(location)
            except Exception as e:
                logger.warning("Location upload error", error=str(e))

    async def _flush(self) -> None:
        async with self._dedup_lock:
            if not self._dedup_map:
                return
            entries = list(self._dedup_map.values())
            self._dedup_map.clear()

        location = Location()
        if self._get_location:
            try:
                location = await self._get_location()
            except Exception as e:
                logger.warning("Failed to get location", error=str(e))

        for i in range(0, len(entries), self._batch_size):
            batch = entries[i : i + self._batch_size]
            await self._upload_batch(batch, location)

    async def _upload_batch(self, entries: list[_DedupEntry], location: Location) -> None:
        gateway_id = self._auth.gateway_id
        if not gateway_id:
            return

        batch_id = str(uuid_mod.uuid4())
        packets_json = []
        for entry in entries:
            pkt = entry.packet.to_gateway_packet(
                location=location, sighting_count=entry.sighting_count,
            )
            pkt["rssi"] = entry.strongest_rssi
            packets_json.append(pkt)

        body: dict[str, Any] = {
            "batchId": batch_id,
            "sentAtMillis": int(time.time() * 1000),
            "packets": packets_json,
        }

        try:
            resp = await self._auth.authenticated_request(
                "POST", f"/api/v1/gateways/{gateway_id}/packets", json_body=body,
            )
            if resp.status_code in (200, 201, 202):
                self._stats_sends += 1
                self._stats_uploaded += len(entries)
                sightings = sum(e.sighting_count for e in entries)
                logger.info(
                    "Batch uploaded",
                    batch_id=batch_id[:8],
                    packets=len(entries),
                    sightings=sightings,
                )
            else:
                logger.warning("Upload failed", status=resp.status_code, body=resp.text[:200])
        except Exception as e:
            logger.error("Upload error", error=str(e))

    async def _upload_location(self, location: Location) -> None:
        gateway_id = self._auth.gateway_id
        if not gateway_id:
            return
        body: dict[str, Any] = {
            "batchId": str(uuid_mod.uuid4()),
            "sentAtMillis": int(time.time() * 1000),
            "locations": [location.to_gateway_dict()],
        }
        try:
            await self._auth.authenticated_request(
                "POST", f"/api/v1/gateways/{gateway_id}/locations", json_body=body,
            )
        except Exception as e:
            logger.warning("Location upload failed", error=str(e))

    def _apply_server_config(self) -> None:
        cfg = self._auth.server_config
        if "uploadBatchSize" in cfg:
            self._batch_size = min(int(cfg["uploadBatchSize"]), 500)
        if "uploadIntervalMs" in cfg:
            self._upload_interval = max(int(cfg["uploadIntervalMs"]) / 1000, 1)
