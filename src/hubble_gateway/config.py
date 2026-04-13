"""Configuration for the Hubble Gateway SDK."""

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

HUBBLE_SERVICE_UUID = "0000FCA6-0000-1000-8000-00805F9B34FB"
TILE_SERVICE_UUID = "0000FEED-0000-1000-8000-00805F9B34FB"
DEFAULT_SERVICE_UUIDS = [HUBBLE_SERVICE_UUID, TILE_SERVICE_UUID]

GATEWAY_API_BASE_URL = "https://gw-api.hubble.com"


class Settings(BaseSettings):
    """Gateway SDK settings loaded from environment variables or .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        env_prefix="HUBBLE_",
    )

    # Required
    sdk_key: str = Field(
        default="",
        description="SDK key from Hubble dashboard (required)",
    )

    # API
    api_base_url: str = Field(
        default=GATEWAY_API_BASE_URL,
        description="Gateway API base URL",
    )
    auth_token_path: str = Field(
        default="~/.hubble-gateway/auth.json",
        description="Path for persisted auth tokens",
    )

    # BLE scanning
    service_uuids: list[str] = Field(
        default=DEFAULT_SERVICE_UUIDS,
        description="BLE service UUIDs to scan for",
    )
    scan_duration_seconds: float = Field(
        default=5.0,
        description="Duration of each BLE scan cycle in seconds",
    )
    ble_adapter: str = Field(
        default="",
        description="BLE adapter to use (e.g. 'hci0', 'hci1' for USB dongle). Empty = default.",
    )

    # Batching and deduplication
    batch_size: int = Field(
        default=500,
        description="Max packets per upload batch",
    )
    upload_interval_seconds: float = Field(
        default=5.0,
        description="Seconds between upload flushes",
    )
    dedup_window_seconds: float = Field(
        default=300.0,
        description="Deduplication window in seconds",
    )

    # Location
    latitude: float | None = Field(
        default=None,
        description="Fixed latitude (used when GPS unavailable)",
    )
    longitude: float | None = Field(
        default=None,
        description="Fixed longitude (used when GPS unavailable)",
    )

    @field_validator("latitude", "longitude", mode="before")
    @classmethod
    def empty_str_to_none(cls, v):
        if v == "" or v is None:
            return None
        return v

    gps_enabled: bool = Field(
        default=False,
        description="Enable GPS auto-detection",
    )
    gps_port: str = Field(
        default="/dev/ttyAMA0",
        description="Serial port for GPS module",
    )
    gps_baud_rate: int = Field(
        default=9600,
        description="Baud rate for GPS serial",
    )
    gps_module: str = Field(
        default="nmea",
        description="GPS module type: 'nmea' (generic NMEA hats), 'zed_f9p' (u-blox UBX binary)",
    )

    # Logging
    log_level: str = Field(
        default="INFO",
        description="Log level: DEBUG, INFO, WARNING, ERROR",
    )
    log_json: bool = Field(
        default=True,
        description="Emit structured JSON logs (disable for human-readable)",
    )
