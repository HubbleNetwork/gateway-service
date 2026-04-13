# Hubble Gateway Service

Ready-to-run BLE gateway daemon for [Hubble Network](https://hubblenetwork.com). Scans for Bluetooth Low Energy devices and uploads sightings to the Hubble cloud. Built on the [hubble-gateway SDK](https://github.com/HubbleNetwork/gateway-sdk-python).

## Raspberry Pi — one-line install

```bash
curl -fsSL https://raw.githubusercontent.com/HubbleNetwork/gateway-service/main/scripts/install.sh \
  | sudo bash -s -- --sdk-key <YOUR_SDK_KEY>
```

With GPS:

```bash
curl -fsSL https://raw.githubusercontent.com/HubbleNetwork/gateway-service/main/scripts/install.sh \
  | sudo bash -s -- --sdk-key <YOUR_SDK_KEY> --gps --gps-port /dev/ttyAMA0
```

Uninstall:

```bash
curl -fsSL https://raw.githubusercontent.com/HubbleNetwork/gateway-service/main/scripts/install.sh \
  | sudo bash -s -- --uninstall
```

The installer sets up a Python venv at `/opt/hubble-gateway`, installs the package, and registers a `hubble-gateway` systemd service that starts on boot.

## Manual install

```bash
pip install hubble-gateway-service
# or
uv pip install hubble-gateway-service
```

## Usage

```bash
hubble-gateway --sdk-key hsk_your_key_here
```

Or with environment variables:

```bash
export HUBBLE_SDK_KEY=hsk_your_key_here
hubble-gateway
```

## Configuration

All settings via CLI flags, environment variables (prefixed `HUBBLE_`), or a `.env` file.

| Environment Variable | CLI Flag | Default | Description |
|---|---|---|---|
| `HUBBLE_SDK_KEY` | `--sdk-key` | *(required)* | SDK key from Hubble dashboard |
| `HUBBLE_API_BASE_URL` | `--api-url` | `https://gw-api.hubble.com` | Gateway API URL |
| `HUBBLE_BLE_ADAPTER` | `--adapter` | *(auto)* | BLE adapter (`hci0`, `hci1`) |
| `HUBBLE_SCAN_DURATION_SECONDS` | — | `5.0` | Seconds per scan cycle |
| `HUBBLE_BATCH_SIZE` | — | `500` | Max packets per upload batch |
| `HUBBLE_UPLOAD_INTERVAL_SECONDS` | — | `5.0` | Seconds between uploads |
| `HUBBLE_DEDUP_WINDOW_SECONDS` | — | `300.0` | Dedup window |
| `HUBBLE_LATITUDE` | `--lat` | — | Fixed latitude |
| `HUBBLE_LONGITUDE` | `--lon` | — | Fixed longitude |
| `HUBBLE_GPS_ENABLED` | `--gps` | `false` | Enable GPS |
| `HUBBLE_GPS_PORT` | `--gps-port` | `/dev/ttyAMA0` | GPS serial port |
| `HUBBLE_GPS_BAUD_RATE` | `--gps-baud` | `9600` | GPS baud rate |
| `HUBBLE_GPS_MODULE` | `--gps-module` | `nmea` | `nmea` or `zed_f9p` |
| `HUBBLE_LOG_LEVEL` | `--log-level` | `INFO` | Log level |
| `HUBBLE_LOG_JSON` | `--log-text` | `true` | JSON logs |

## GPS Support

| Module | Flag | Description |
|---|---|---|
| NMEA hat | `--gps --gps-port /dev/ttyAMA0` | Adafruit, SparkFun, etc. |
| u-blox ZED-F9P | `--gps --gps-module zed_f9p --gps-port /dev/ttyAMA3 --gps-baud 38400` | High-precision UBX |
| gpsd | `--gps` | Falls back to gpsd when serial unavailable |
| Fixed | `--lat 37.77 --lon -122.42` | No GPS hardware |

## USB BLE Dongle

```bash
hciconfig                          # find your adapter
hubble-gateway --sdk-key $KEY --adapter hci1
```

## Running as a systemd service

The [one-line installer](#raspberry-pi--one-line-install) handles this automatically. For manual setup:

```ini
# /etc/systemd/system/hubble-gateway.service
[Unit]
Description=Hubble Network BLE Gateway
After=network-online.target bluetooth.target
Wants=network-online.target

[Service]
Type=simple
EnvironmentFile=/opt/hubble-gateway/.env
ExecStart=/opt/hubble-gateway/venv/bin/hubble-gateway
Restart=always
RestartSec=10
WatchdogSec=300

[Install]
WantedBy=multi-user.target
```

## Architecture

```
hubble-gateway-service (this repo)
  └─ daemon.py          — orchestration, signal handling, stats loop
  └─ cli.py             — argument parsing, env wiring
  └─ install.sh         — one-line Pi installer

hubble-gateway SDK (gateway-sdk-python)
  └─ Scanner            — BLE scanning via bleak
  └─ GatewaySender      — packet batching + dedup + upload
  └─ GatewayAuth        — SDK key registration + token lifecycle
  └─ LocationProvider    — GPS (NMEA, UBX, gpsd) + fixed
  └─ Settings            — pydantic-settings config
  └─ BLEPacket, Location — data models
```

## Building a custom gateway

If you need more control, use the SDK directly:

```bash
pip install hubble-gateway
```

```python
from hubble_gateway import Scanner, GatewaySender, GatewayAuth

# See https://github.com/HubbleNetwork/gateway-sdk-python
```

## License

Apache License 2.0 — see [LICENSE](LICENSE).
