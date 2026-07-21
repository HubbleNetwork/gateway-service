# Hubble Gateway — Raspberry Pi image

Build a ready-to-flash Raspberry Pi OS image that runs the Hubble Network BLE
gateway automatically on boot, using
[`rpi-image-gen`](https://github.com/raspberrypi/rpi-image-gen).

The intended flow:

1. **You** build a `.img` once with `rpi-image-gen`.
2. **An operator** flashes it with **Raspberry Pi Imager**, uses Imager's
   **OS Customization** to set **Wi‑Fi (or leaves it for ethernet)**, hostname
   and SSH, then drops the **SDK key** onto the boot partition.
3. On boot the Pi provisions itself and the gateway starts.

---

## What's in this directory

| Path | Purpose |
|---|---|
| `config/hubble-gateway.yaml` | Build config — selects device/image/networking and Hubble options |
| `layer/hubble-gateway.yaml` | Custom layer — installs the daemon, seeds config, enables services |
| `layer/hubble-gateway.rootfs-overlay/` | Files baked into the image (systemd units, provisioner, boot config example) |
| `bdebstrap/customize90-hubble` | Customize-phase hook that enables the services after the overlay is applied |
| `hubble-gateway.rpi-imager-manifest` | Local Imager manifest so the Customization wizard appears for the custom `.img` |

---

## 1. Build the image

On a Debian/Ubuntu amd64 host (cross-build) or a Pi:

```bash
git clone https://github.com/raspberrypi/rpi-image-gen.git
cd rpi-image-gen
sudo ./install_deps.sh

# Build using this project as the source dir (-S) so the custom layer is found.
./rpi-image-gen build -S /path/to/gateway-service/rpi-image -c hubble-gateway.yaml
```

The resulting image is written under `rpi-image-gen`'s work/output directory
(reported at the end of the build, named `hubble-gateway`). Compress it for
Imager if you like:

```bash
xz -T0 -k hubble-gateway.img
```

### Building in CI

`.github/workflows/rpi-image.yml` builds the image on GitHub's native arm64
runners. Trigger it manually (**Actions → Raspberry Pi Image → Run workflow**)
to pick the device model, `hubble-gateway` version, and install method; or push
a tag `image-v*` to build the default models (`rpi5`, `rpi4`) and attach the
compressed images to a GitHub Release. The workflow writes a small `ci.yaml`
that `include:`s `hubble-gateway.yaml` and overrides `device.layer` /
`hubble.version` / `hubble.install_method` per run.

### Build-time options

Edit `config/hubble-gateway.yaml`:

- `device.layer` — `rpi5` (default), `rpi4`, `rpi3`, `zero2w`, `cm4`, `cm5`.
- `hubble.sdk_key` — bake a key into the image (leave empty to provision at flash time).
- `hubble.lat` / `hubble.lon` or `hubble.gps` — location (required by the daemon).
- `hubble.install_method` — `binary` (prebuilt aarch64, default) or `pip` (from PyPI).
- `hubble.version` — `latest` or a release tag like `v0.1.0`.
- `ieee80211.regdom` — default wireless country.

> The daemon requires a location. Set `hubble.lat`+`hubble.lon` or `hubble.gps`,
> or provide them per-device in `hubble-gateway.conf` (below). Without a location
> the service starts, fails fast, and retries every 15s until provisioned.

---

## 2. Flash with Raspberry Pi Imager

Imager 2.x won't show OS Customization for a plain local `.img` unless it knows
the image's customization format. Point it at the included manifest:

1. Edit `hubble-gateway.rpi-imager-manifest` and set the `url` to the absolute
   path of your image, e.g. `file:///home/you/hubble-gateway.img.xz`.
2. In Imager: **App Options → Content Repository → Use custom** → select
   `hubble-gateway.rpi-imager-manifest`. (Re-select after each Imager restart.)
3. **Choose OS → Hubble Gateway**, choose your storage, then open
   **OS Customization** (the gear / Ctrl+Shift+X).

In OS Customization set:

- **Wi‑Fi** — SSID, password, country. *(Skip this to use ethernet — DHCP just
  works, nothing to configure.)*
- **Hostname**, **SSH** (enable + your public key), **locale** as desired.

These map to Imager's `firstrun.sh`, which this image honors via the
`raspberrypi-sys-mods` package (it configures NetworkManager, SSH and hostname).

> **Why isn't the SDK key a field here?** Imager's customization fields are a
> fixed set (hostname, user, wifi, SSH, locale). Imager has no mechanism for a
> custom "SDK Key" field, so the key is supplied via the boot partition instead
> (next step).

---

## 3. Provide the SDK key (and optional location)

After flashing, re-plug the card/USB. A small **`bootfs`** (FAT) partition
mounts on your computer containing **`hubble-gateway.conf.example`**.

1. Copy/rename it to **`hubble-gateway.conf`** on that same partition.
2. Set at least the SDK key and a location:

   ```ini
   SDK_KEY=hsk_your_key_here
   LAT=37.7749
   LON=-122.4194
   # or instead of LAT/LON:
   # GPS=true
   ```

3. Eject and boot the Pi.

On boot, `hubble-provision.service` reads the file, writes
`/opt/hubble-gateway/.env`, optionally configures Wi‑Fi (if you used `WIFI_*`
keys instead of Imager), then renames the file to `hubble-gateway.conf.applied`
so the key isn't left in plaintext. `hubble-gateway.service` then starts.

`hubble-gateway.conf` keys: `SDK_KEY`, `LAT`, `LON`, `GPS`, `GPS_PORT`,
`GPS_BAUD`, `GPS_MODULE`, `ADAPTER`, `API_URL`, `WIFI_SSID`, `WIFI_PSK`,
`WIFI_COUNTRY` (also accepts `HUBBLE_*` names).

---

## 4. Verify on the device

```bash
systemctl status hubble-provision   # one-shot; shows what was applied
systemctl status hubble-gateway     # the running daemon
journalctl -u hubble-gateway -f     # live logs
cat /opt/hubble-gateway/.env        # effective config (root only)
```

---

## How it fits together

```
Raspberry Pi Imager
  ├─ OS Customization ─► firstrun.sh ─► raspberrypi-sys-mods ─► NetworkManager (wifi), SSH, hostname
  └─ (ethernet: nothing needed — NetworkManager DHCP)

Boot partition (bootfs, FAT)
  └─ hubble-gateway.conf ─► hubble-provision.service ─► /opt/hubble-gateway/.env

systemd (multi-user.target)
  ├─ hubble-provision.service   (oneshot, Before hubble-gateway)
  └─ hubble-gateway.service     (After provision + network-online + bluetooth; Restart=always)
        └─ /opt/hubble-gateway/hubble-gateway   (PyApp binary or pip venv)
```

Networking is **NetworkManager** (single `network-activator`), BLE is **BlueZ**,
time via **systemd-timesyncd**. The base mirrors `bookworm-minbase` with the
network stack swapped to NetworkManager and BlueZ + wireless regulatory added.
