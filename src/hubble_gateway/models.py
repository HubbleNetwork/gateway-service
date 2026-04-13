"""Data models for BLE packets and locations."""

import base64
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field


def uuid_to_16bit(full_uuid: str) -> str:
    """Extract 16-bit short form from a full 128-bit BLE UUID.

    ``0000FCA6-0000-1000-8000-00805F9B34FB`` -> ``FCA6``
    """
    return full_uuid[4:8].upper()


class Location(BaseModel):
    """Geographic location."""

    latitude: float | None = None
    longitude: float | None = None
    altitude: float | None = None
    horizontal_accuracy: float | None = None
    vertical_accuracy: float | None = None
    source: str = "unknown"
    gps_state: str = "off"
    fix_count: int = 0
    hdop: float | None = None
    sat_count: int | None = None
    speed_ms: float | None = None
    course_deg: float | None = None

    def to_gateway_dict(self, timestamp_ms: int | None = None) -> dict[str, Any]:
        """Convert to gateway-api location format."""
        result: dict[str, Any] = {
            "latitude": self.latitude if self.latitude is not None else 0.0,
            "longitude": self.longitude if self.longitude is not None else 0.0,
            "horizontalAccuracyMeters": (
                self.horizontal_accuracy if self.horizontal_accuracy is not None else 10.0
            ),
            "timestampMillis": timestamp_ms or int(datetime.now(timezone.utc).timestamp() * 1000),
        }
        if self.altitude is not None:
            result["altitude"] = self.altitude
        if self.vertical_accuracy is not None:
            result["verticalAccuracyMeters"] = self.vertical_accuracy
        return result


class BLEPacket(BaseModel):
    """A single BLE advertisement packet."""

    device_address: str = Field(description="BLE device MAC address")
    device_name: str | None = Field(default=None)
    rssi: int = Field(description="RSSI in dBm")
    service_uuids: list[str] = Field(default_factory=list)
    manufacturer_data: dict[int, bytes] = Field(default_factory=dict)
    service_data: dict[str, bytes] = Field(default_factory=dict)
    tx_power: int | None = Field(default=None)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    service_uuid: str | None = Field(
        default=None,
        description="Matched service UUID (set by scanner)",
    )

    class Config:
        json_encoders = {
            bytes: lambda v: v.hex(),
            datetime: lambda v: v.isoformat(),
        }

    def get_matched_service_data(self) -> bytes | None:
        """Get service data for the matched service UUID."""
        if self.service_uuid:
            target = self.service_uuid.lower()
            for uid, data in self.service_data.items():
                if uid.lower() == target:
                    return data
        for uid, data in self.service_data.items():
            return data
        return None

    @property
    def service_data_hex(self) -> str:
        """Hex of matched service data (dedup key component)."""
        data = self.get_matched_service_data()
        return data.hex() if data else ""

    @property
    def service_uuid_16bit(self) -> str | None:
        """16-bit short form of matched UUID (e.g. 'FCA6')."""
        if self.service_uuid:
            return uuid_to_16bit(self.service_uuid)
        return None

    def to_gateway_packet(
        self, location: Location | None = None, sighting_count: int = 1
    ) -> dict[str, Any]:
        """Convert to gateway-api packet format."""
        payload_bytes = self.get_matched_service_data()
        service_data_b64 = (
            base64.b64encode(payload_bytes).decode() if payload_bytes else None
        )
        ts_ms = int(self.timestamp.timestamp() * 1000)

        packet: dict[str, Any] = {
            "deviceAddress": self.device_address,
            "rssi": self.rssi,
            "timestampMillis": ts_ms,
            "serviceUuid": self.service_uuid_16bit,
            "sightingCount": sighting_count,
        }
        if service_data_b64:
            packet["serviceData"] = service_data_b64
        if location:
            packet["location"] = location.to_gateway_dict(timestamp_ms=ts_ms)
        return packet
