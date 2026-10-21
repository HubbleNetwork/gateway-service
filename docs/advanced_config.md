# Advanced configuration

Reference for configuring `hubble-gateway`, plus manual install methods for when
the [Raspberry Pi image](../rpi-image/README.md) or the
[one-line installer](../README.md#existing-linux-machine--one-line-install)
don't fit your setup.

## Contents

- [Running the daemon](#running-the-daemon)
- [Configuration reference](#configuration-reference)
- [GPS support](#gps-support)
- [USB BLE dongle](#usb-ble-dongle)
- [Manual install](#manual-install)
  - [pip / uv](#pip--uv)
  - [Download the binary directly](#download-the-binary-directly)
  - [systemd service](#systemd-service)
- [Read-only root filesystems](#read-only-root-filesystems)
- [Installer options](#installer-options)
- [Architecture](#architecture)
- [Building a custom gateway](#building-a-custom-gateway)

## Running the daemon

```bash
hubble-gateway --sdk-key hsk_your_key_here --lat 37.7749 --lon -122.4194
```

Or with environment variables:

```bash
export HUBBLE_SDK_KEY=hsk_your_key_here
export HUBBLE_LATITUDE=37.7749
export HUBBLE_LONGITUDE=-122.4194
hubble-gateway
```

The daemon requires a location: pass `--lat`/`--lon` for a fixed position, or
`--gps` to read one from a GPS module. Without a location it exits with a clear
error.

## Configuration reference

All settings can be provided via CLI flags, environment variables (prefixed
`HUBBLE_`), or a `.env` file.

| Environment Variable | CLI Flag | Default | Description |
|---|---|---|---|
| `HUBBLE_SDK_KEY` | `--sdk-key` | *(required)* | SDK key from Hubble dashboard |
| `HUBBLE_API_BASE_URL` | `--api-url` | `https://gw-api.hubble.com` | Gateway API URL |
| `HUBBLE_BLE_ADAPTER` | `--adapter` | *(auto)* | BLE adapter (`hci0`, `hci1`) |
| `HUBBLE_SERVICE_UUIDS` | — | *(none)* | Extra BLE service UUIDs to scan for, as a JSON list of 128-bit UUIDs. Scan-only: not uploaded ² |
| `HUBBLE_SCAN_DURATION_SECONDS` | — | `5.0` | Seconds per scan cycle |
| `HUBBLE_BATCH_SIZE` | — | `500` | Max packets per upload batch ¹ |
| `HUBBLE_UPLOAD_INTERVAL_SECONDS` | — | `60.0` | Seconds between uploads ¹ |
| `HUBBLE_DEDUP_WINDOW_SECONDS` | — | `300.0` | Dedup window ¹ |
| `HUBBLE_LATITUDE` | `--lat` | — | Fixed latitude |
| `HUBBLE_LONGITUDE` | `--lon` | — | Fixed longitude |
| `HUBBLE_GPS_ENABLED` | `--gps` | `false` | Enable GPS |
| `HUBBLE_GPS_PORT` | `--gps-port` | `/dev/ttyAMA0` | GPS serial port |
| `HUBBLE_GPS_BAUD_RATE` | `--gps-baud` | `9600` | GPS baud rate |
| `HUBBLE_GPS_MODULE` | `--gps-module` | `nmea` | `nmea` or `zed_f9p` |
| `HUBBLE_LOG_LEVEL` | `--log-level` | `INFO` | Log level |
| `HUBBLE_LOG_JSON` | `--log-text` | `true` | JSON logs |
| `HUBBLE_AUTH_TOKEN_PATH` | — | `~/.hubble-gateway/auth.json` | Where the gateway saves its auth tokens after registering |

¹ Local fallback. When the Hubble cloud sends a server config for this gateway
(`uploadBatchSize`, `uploadIntervalMs`, `dedupWindowMs`), the server value
wins. The gateway applies a new server config at once, with no restart, on
registration, heartbeat or token refresh. A cleared server config returns the
gateway to these local values. The dedup window holds across uploads: a device
seen again inside the window is not uploaded again.

² A JSON list, e.g.
`HUBBLE_SERVICE_UUIDS='["0000180F-0000-1000-8000-00805F9B34FB"]'`. The gateway
always scans for and uploads Hubble's `FCA6` advertisements, plus the payload
services enabled for its SDK key (such as Tile's `FEED`). Services listed here
are scanned only; their advertisements are not uploaded. Before 0.1.4 this
setting defaulted to FCA6 and FEED and its services were uploaded; to keep
uploading a service you added here, enable it for your SDK key instead.

## GPS support

| Module | Flag | Description |
|---|---|---|
| NMEA hat | `--gps --gps-port /dev/ttyAMA0` | Adafruit, SparkFun, etc. |
| u-blox ZED-F9P | `--gps --gps-module zed_f9p --gps-port /dev/ttyAMA3 --gps-baud 38400` | High-precision UBX |
| gpsd | `--gps` | Falls back to gpsd when serial unavailable |
| Fixed | `--lat 37.77 --lon -122.42` | No GPS hardware |

## USB BLE dongle

List the available adapters and point the gateway at the one you want:

```bash
hciconfig                          # find your adapter (hci0, hci1, ...)
hubble-gateway --sdk-key $KEY --adapter hci1
```

> `hciN` numbering is not guaranteed stable across reboots when more than one
> radio is present (e.g. onboard Bluetooth + a USB dongle). Confirm the adapter
> in use with `bluetoothctl show` (`Discovering: yes` on the active controller).

## Manual install

### pip / uv

```bash
pip install hubble-gateway-service
# or
uv pip install hubble-gateway-service
```

### Download the binary directly

Pre-built single-file binaries for each release — no Python needed. They're
attached to the `v*` releases, not the `image-v*` releases. GitHub's "latest"
release is always an image release, so `releases/latest/download/...` links
don't work for these binaries. Look up the newest `v*` tag first:

```bash
sudo mkdir -p /opt/hubble-gateway/tmp   # the systemd unit below uses tmp/ as TMPDIR
VERSION=$(curl -fsSL https://api.github.com/repos/HubbleNetwork/gateway-service/releases \
  | grep -o '"tag_name": *"v[^"]*"' | head -1 | cut -d'"' -f4)

# Raspberry Pi (aarch64)
sudo curl -fsSL "https://github.com/HubbleNetwork/gateway-service/releases/download/${VERSION}/hubble-gateway-aarch64-linux" \
  -o /opt/hubble-gateway/hubble-gateway && sudo chmod +x /opt/hubble-gateway/hubble-gateway

# x86_64 Linux
sudo curl -fsSL "https://github.com/HubbleNetwork/gateway-service/releases/download/${VERSION}/hubble-gateway-x86_64-linux" \
  -o /opt/hubble-gateway/hubble-gateway && sudo chmod +x /opt/hubble-gateway/hubble-gateway
```

Or pin a specific version, e.g. `VERSION=v0.1.2`.

The binaries need glibc 2.34 or newer. On musl systems (Alpine, some embedded
images), use pip instead.

On first run the binary unpacks its Python runtime and installs its
dependencies from PyPI (about 200 MB, and it needs internet access once). Later
runs start immediately and work offline.

### systemd service

The [one-line installer](../README.md#existing-linux-machine--one-line-install)
sets this up automatically. To do it by hand, copy the unit that matches how you
installed into `/etc/systemd/system/hubble-gateway.service`:

| Install | Example unit |
|---|---|
| Binary in `/opt/hubble-gateway` | [`hubble-gateway.service`](../examples/systemd/hubble-gateway.service) |
| pip, venv in `/opt/hubble-gateway/venv` | [`hubble-gateway-pip.service`](../examples/systemd/hubble-gateway-pip.service) |
| Binary on a read-only root, in `/data/hubble-gateway` | [`hubble-gateway-readonly-root.service`](../examples/systemd/hubble-gateway-readonly-root.service) |

The binary unit:

```ini
[Unit]
Description=Hubble Network BLE Gateway
After=network-online.target bluetooth.target
Wants=network-online.target

[Service]
Type=simple
Environment=XDG_CACHE_HOME=/opt/hubble-gateway/cache
Environment=XDG_DATA_HOME=/opt/hubble-gateway/share
Environment=TMPDIR=/opt/hubble-gateway/tmp
Environment=HUBBLE_AUTH_TOKEN_PATH=/opt/hubble-gateway/auth.json
EnvironmentFile=/opt/hubble-gateway/.env
ExecStart=/opt/hubble-gateway/hubble-gateway
Restart=always
RestartSec=10
WatchdogSec=300
NotifyAccess=all

[Install]
WantedBy=multi-user.target
```

Put your settings in `/opt/hubble-gateway/.env` (one `HUBBLE_*=value` per line;
see the [configuration reference](#configuration-reference)) and make it
readable only by root, since it holds your SDK key:

```bash
sudo chmod 600 /opt/hubble-gateway/.env
sudo systemctl daemon-reload
sudo systemctl enable --now hubble-gateway
sudo journalctl -u hubble-gateway -f
```

`EnvironmentFile=` must point at a file that exists. If it doesn't, systemd
logs `Failed to load environment files: No such file or directory` and retries
forever without starting the gateway.

For another install directory, `sh scripts/install.sh --print-unit --install-dir <DIR>`
prints the unit to use (add `--pip` for a pip install).

## Read-only root filesystems

Embedded images (Yocto, OTA A/B systems) often mount `/` read-only and keep a
separate writable partition such as `/data`. The gateway writes files in four
places, and by default all of them are under `$HOME`:

| What | Default location | Moved with |
|---|---|---|
| Unpacked Python runtime (binary only) | `~/.local/share/pyapp` | `XDG_DATA_HOME` |
| Download cache and lock files (binary only) | `~/.cache` | `XDG_CACHE_HOME` |
| Temporary files during first-run unpacking | `/tmp` | `TMPDIR` |
| Auth tokens saved after registering | `~/.hubble-gateway/auth.json` | `HUBBLE_AUTH_TOKEN_PATH` |

The units above set all four to directories inside the install directory, so a
gateway installed on a writable partition never writes anywhere else. The
one-line installer detects a read-only `/opt` and installs to `/data`, `/persist`
or `/var/lib` instead. It skips any location that is wiped on reboot, such as
tmpfs or an overlay whose writable layer is on tmpfs. Choose a location
yourself with `--install-dir`.

The service also needs `/etc/systemd/system` to be writable. Many read-only
images make `/etc` an overlay stored on the data partition, so this usually
works.

To run the gateway by hand on such a system, set the same variables. `sudo`
drops environment variables by default, so pass them with `env`:

```bash
sudo env XDG_CACHE_HOME=/data/hubble-gateway/cache \
         XDG_DATA_HOME=/data/hubble-gateway/share \
         TMPDIR=/data/hubble-gateway/tmp \
         HUBBLE_AUTH_TOKEN_PATH=/data/hubble-gateway/auth.json \
         /data/hubble-gateway/hubble-gateway --sdk-key hsk_your_key_here --lat 37.7749 --lon -122.4194
```

`TMPDIR` must point at a directory that exists.

## Installer options

`scripts/install.sh` is POSIX `sh`, so it also runs on BusyBox systems
without bash.

| Option | Description |
|---|---|
| `--sdk-key KEY` | SDK key (required) |
| `--lat LAT`, `--lon LON` | Fixed location |
| `--gps`, `--gps-port`, `--gps-baud`, `--gps-module` | GPS settings, as in the [configuration reference](#configuration-reference) |
| `--adapter ADAPTER` | BLE adapter (`hci0`, `hci1`) |
| `--install-dir DIR` | Install location. Default: `/opt/hubble-gateway`, or the first persistent writable one of `/data`, `/persist`, `/var/lib` |
| `--version TAG` | Binary release to install, e.g. `v0.1.2`. Default: newest |
| `--pip` | Install with pip instead of the binary |
| `--print-unit` | Print the systemd unit the installer would write, then exit |
| `--uninstall` | Stop and remove the service and the install directory |

The installer runs the binary once before creating the service, so a missing
network connection or an incompatible system shows up as an install error
rather than as a service restart loop. Install output goes to `install.log` in
the install directory.

An existing gateway's tokens in `/root/.hubble-gateway/auth.json` are copied to
the new location, so re-installing doesn't register the gateway again.

## Architecture

```
hubble-gateway-service (this repo)
  ├─ daemon.py            orchestration, signal handling, stats loop
  ├─ cli.py               argument parsing, env wiring
  ├─ systemd.py           sd_notify watchdog pings (WatchdogSec=300)
  ├─ install.sh           one-line installer (binary or pip; POSIX sh)
  ├─ examples/systemd/    unit files, kept equal to install.sh --print-unit by tests
  └─ release.yml          GitHub Actions → PyApp single-binary builds

hubble-gateway SDK (gateway-sdk-python)
  ├─ Scanner              BLE scanning via bleak
  ├─ GatewaySender        packet batching + dedup + upload
  ├─ GatewayAuth          SDK key registration + token lifecycle
  ├─ LocationProvider     GPS (NMEA, UBX, gpsd) + fixed
  ├─ Settings             pydantic-settings config
  └─ BLEPacket, Location  data models
```

The service binary is built with [PyApp](https://github.com/ofek/pyapp) — a Rust
wrapper that embeds a Python distribution. First run unpacks Python and installs
the dependencies from PyPI; subsequent runs start instantly.

## Building a custom gateway

If you need more control, use the SDK directly:

```bash
pip install hubble-gateway-sdk-python
```

```python
from hubble_gateway import Scanner, GatewaySender, GatewayAuth

# See https://github.com/HubbleNetwork/gateway-sdk-python
```
