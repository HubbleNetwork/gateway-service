# Hubble Gateway SDK for Python

Open-source BLE gateway that scans for Bluetooth Low Energy devices and uploads sightings to the [Hubble Network](https://hubblenetwork.com) cloud. Runs as a background daemon on a Raspberry Pi or any Linux host with a BLE adapter.

## Features

- **Multi-UUID BLE scanning** — Hubble (`FCA6`) and Tile (`FEED`) service UUIDs out of the box
- **USB dongle support** — use the built-in BLE adapter or plug in a USB BLE dongle (`hci1`)
- **GPS integration** — serial NMEA hats, u-blox UBX receivers (ZED-F9P), or `gpsd`
- **Automatic registration** — SDK-key-based auth with token persistence across restarts
- **Deduplication** — Android-SDK-compatible `(address, uuid, payload)` dedup with sighting counts
- **Structured logging** — JSON or human-readable logs via `structlog`
- **Graceful shutdown** — responds to `SIGTERM`/`SIGINT` cleanly

## Quick Start

### 1. Install

```bash
pip install hubble-gateway
```

With GPS support (serial NMEA or gpsd):

```bash
pip install "hubble-gateway[gps]"
```

### 2. Get your SDK key

Sign up at [dashboard.hubble.com](https://dashboard.hubble.com) and create a gateway SDK key.

### 3. Run

```bash
hubble-gateway --sdk-key hsk_your_key_here
```

Or use environment variables:

```bash
export HUBBLE_SDK_KEY=hsk_your_key_here
hubble-gateway
```

## Configuration

All settings can be passed via CLI flags, environment variables (prefixed with `HUBBLE_`), or a `.env` file.

| Environment Variable | CLI Flag | Default | Description |
|---|---|---|---|
| `HUBBLE_SDK_KEY` | `--sdk-key` | *(required)* | SDK key from Hubble dashboard |
| `HUBBLE_API_BASE_URL` | `--api-url` | `https://gw-api.hubble.com` | Gateway API URL |
| `HUBBLE_BLE_ADAPTER` | `--adapter` | *(auto)* | BLE adapter (`hci0`, `hci1`, etc.) |
| `HUBBLE_SERVICE_UUIDS` | — | FCA6, FEED | BLE service UUIDs to scan |
| `HUBBLE_SCAN_DURATION_SECONDS` | — | `5.0` | Seconds per scan cycle |
| `HUBBLE_BATCH_SIZE` | — | `500` | Max packets per upload batch |
| `HUBBLE_UPLOAD_INTERVAL_SECONDS` | — | `5.0` | Seconds between uploads |
| `HUBBLE_DEDUP_WINDOW_SECONDS` | — | `300.0` | Deduplication window |
| `HUBBLE_LATITUDE` | `--lat` | — | Fixed latitude |
| `HUBBLE_LONGITUDE` | `--lon` | — | Fixed longitude |
| `HUBBLE_GPS_ENABLED` | `--gps` | `false` | Enable GPS |
| `HUBBLE_GPS_PORT` | `--gps-port` | `/dev/ttyAMA0` | GPS serial port |
| `HUBBLE_GPS_BAUD_RATE` | `--gps-baud` | `9600` | GPS baud rate |
| `HUBBLE_GPS_MODULE` | `--gps-module` | `nmea` | `nmea` or `zed_f9p` |
| `HUBBLE_LOG_LEVEL` | `--log-level` | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR` |
| `HUBBLE_LOG_JSON` | `--log-text` | `true` | JSON logs (use `--log-text` for readable) |

## GPS Support

### Generic NMEA GPS Hat

Most Raspberry Pi GPS hats (Adafruit Ultimate GPS, SparkFun GPS, etc.) output NMEA over a serial UART:

```bash
hubble-gateway --sdk-key $KEY --gps --gps-port /dev/ttyAMA0
```

### u-blox ZED-F9P (UBX binary)

For high-precision GNSS receivers:

```bash
hubble-gateway --sdk-key $KEY --gps --gps-module zed_f9p --gps-port /dev/ttyAMA3 --gps-baud 38400
```

### gpsd

If you have `gpsd` running and `gpsd-py3` installed, the SDK will fall back to it when serial GPS is unavailable.

### Fixed Location

No GPS? Just set static coordinates:

```bash
hubble-gateway --sdk-key $KEY --lat 37.7749 --lon -122.4194
```

## USB BLE Dongle

To use an external USB BLE adapter instead of (or alongside) the built-in one:

```bash
# Find your adapter
hciconfig

# Use hci1 (USB dongle)
hubble-gateway --sdk-key $KEY --adapter hci1
```

## Running as a Service

Create a systemd service for automatic start on boot:

```ini
# /etc/systemd/system/hubble-gateway.service
[Unit]
Description=Hubble Network BLE Gateway
After=network-online.target bluetooth.target
Wants=network-online.target

[Service]
Type=simple
User=root
Environment=HUBBLE_SDK_KEY=hsk_your_key_here
Environment=HUBBLE_GPS_ENABLED=true
Environment=HUBBLE_GPS_PORT=/dev/ttyAMA0
ExecStart=/usr/local/bin/hubble-gateway
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now hubble-gateway
sudo journalctl -u hubble-gateway -f
```

## Development

```bash
git clone https://github.com/HubbleNetwork/gateway-sdk-python.git
cd gateway-sdk-python
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Supported Hardware

| Hardware | Type | Support |
|---|---|---|
| Raspberry Pi 3B+/4/5 | Host | Built-in BLE + GPIO GPS |
| Any Linux with BlueZ | Host | Internal BLE adapter |
| USB BLE 5.0 dongle | BLE | Via `--adapter hci1` |
| Adafruit Ultimate GPS | GPS | NMEA serial |
| SparkFun GPS-RTK | GPS | NMEA serial |
| u-blox ZED-F9P | GPS | UBX binary (`zed_f9p`) |
| u-blox NEO-M9N | GPS | UBX binary (`zed_f9p`) |
| Any gpsd-compatible | GPS | Via `gpsd` fallback |

## License

Apache License 2.0 — see [LICENSE](LICENSE).
