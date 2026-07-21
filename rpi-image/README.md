# Hubble Gateway — Raspberry Pi image

A ready-to-flash Raspberry Pi OS image that runs the Hubble Network BLE gateway
automatically on boot. Images are built by CI (see
[Building the image](#building-the-image-maintainers)); as an operator you just
**download a prebuilt image and flash it**.

The flow:

1. **Install Raspberry Pi Imager.**
2. **Download** the image for your Pi model via the direct link below.
3. **Flash** it with Imager and set **Wi‑Fi** (or leave it for ethernet).
4. **Edit `hubble-gateway.conf`** on the boot partition with your SDK key + location.
5. Boot the Pi — it provisions itself and the gateway starts.

---

## 1. Install Raspberry Pi Imager

Download and install it from **<https://www.raspberrypi.com/software/>**, or use a
direct link:

- **Windows** — <https://downloads.raspberrypi.org/imager/imager_latest.exe>
- **macOS** — <https://downloads.raspberrypi.org/imager/imager_latest.dmg>
- **Linux (Debian/Ubuntu)** — <https://downloads.raspberrypi.org/imager/imager_latest_amd64.deb>

You'll need **Imager 2.x** (any recent install).

---

## 2. Download the image

Direct links to the latest published image per Raspberry Pi model:

- **Pi 5** — <https://github.com/HubbleNetwork/gateway-service/releases/latest/download/hubble-gateway-rpi5.img.xz>
- **Pi 4** — <https://github.com/HubbleNetwork/gateway-service/releases/latest/download/hubble-gateway-rpi4.img.xz>
- **Pi 3** — <https://github.com/HubbleNetwork/gateway-service/releases/latest/download/hubble-gateway-rpi3.img.xz>
- **Zero 2 W** — <https://github.com/HubbleNetwork/gateway-service/releases/latest/download/hubble-gateway-zero2w.img.xz>
- **CM4** — <https://github.com/HubbleNetwork/gateway-service/releases/latest/download/hubble-gateway-cm4.img.xz>
- **CM5** — <https://github.com/HubbleNetwork/gateway-service/releases/latest/download/hubble-gateway-cm5.img.xz>

These are permanent links that always resolve to the newest published release
(`releases/latest/download/...`); the asset filenames don't change between
versions.

No need to decompress — Imager reads `.img.xz` directly. You also need the small
manifest file `hubble-gateway.rpi-imager-manifest` from this directory (it lets
Imager show the customization wizard for a local image).

> Browse all versions on the
> [Releases page](https://github.com/HubbleNetwork/gateway-service/releases). If
> your model isn't published yet, a maintainer can build it — see
> [Building the image](#building-the-image-maintainers).

---

## 3. Flash with Raspberry Pi Imager (and set Wi‑Fi)

Imager 2.x won't show OS Customization for a plain local image unless it knows
the image's customization format. Point it at the included manifest:

1. Edit `hubble-gateway.rpi-imager-manifest` and set the `url` to the absolute
   path of the image you downloaded, e.g.
   `file:///home/you/hubble-gateway-rpi5.img.xz`.
2. In Imager: **App Options → Content Repository → Use custom** → select
   `hubble-gateway.rpi-imager-manifest`. (Re-select after each Imager restart.)
3. **Choose OS → Hubble Gateway**, choose your storage, then open
   **OS Customization** (the gear / Ctrl+Shift+X).

In OS Customization set:

- **Wi‑Fi** — SSID, password, country. *(Skip this to use ethernet — DHCP just
  works, nothing to configure.)*
- **Hostname**, **SSH** (enable + your public key), **locale** as desired.

Then **Save** and **Write** the image.

These fields map to Imager's `firstrun.sh`, which this image honors via the
`raspberrypi-sys-mods` package (it configures NetworkManager, SSH and hostname).

> **Why isn't the SDK key a field here?** Imager's customization fields are a
> fixed set (hostname, user, wifi, SSH, locale). Imager has no mechanism for a
> custom "SDK Key" field, so the key is supplied via the boot partition instead
> (next step).

---

## 4. Edit `hubble-gateway.conf` (SDK key + location)

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

> The daemon requires a location. Provide `LAT`+`LON` or `GPS=true`. Without a
> location the service starts, fails fast, and retries every 15s until you set
> one.

---

## 5. Verify on the device

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

---

## Building the image (maintainers)

Images are normally built by GitHub Actions
(`.github/workflows/rpi-image.yml`) on native arm64 runners:

- **Manually**: **Actions → Raspberry Pi Image → Run workflow**, choosing the
  device model, `hubble-gateway` version, and install method.
- **On a tag** `image-v*`: builds the default models (`rpi5`, `rpi4`) and
  attaches the compressed images to a GitHub Release.

The workflow writes a small `ci.yaml` that `include:`s `hubble-gateway.yaml` and
overrides `device.layer` / `hubble.version` / `hubble.install_method` per run.

### Build locally

On a Debian/Ubuntu amd64 host (cross-build) or a Pi:

```bash
git clone https://github.com/raspberrypi/rpi-image-gen.git
cd rpi-image-gen
sudo ./install_deps.sh

# Build using this project as the source dir (-S) so the custom layer is found.
./rpi-image-gen build -S /path/to/gateway-service/rpi-image -c hubble-gateway.yaml

# Compress for Imager:
xz -T0 -k <work-output-dir>/hubble-gateway.img
```

### Build-time options

Edit `config/hubble-gateway.yaml`:

- `device.layer` — `rpi5` (default), `rpi4`, `rpi3`, `zero2w`, `cm4`, `cm5`.
- `hubble.sdk_key` — bake a key into the image (leave empty to provision at flash time).
- `hubble.lat` / `hubble.lon` or `hubble.gps` — default location.
- `hubble.install_method` — `binary` (prebuilt aarch64, default) or `pip` (from PyPI).
- `hubble.version` — `latest` or a release tag like `v0.1.0`.
- `ieee80211.regdom` — default wireless country.

### What's in this directory

| Path | Purpose |
|---|---|
| `config/hubble-gateway.yaml` | Build config — selects device/image/networking and Hubble options |
| `layer/hubble-gateway.yaml` | Custom layer — installs the daemon, seeds config, enables services |
| `layer/hubble-gateway.rootfs-overlay/` | Files baked into the image (systemd units, provisioner, boot config example) |
| `bdebstrap/customize90-hubble` | Customize-phase hook that enables the services after the overlay is applied |
| `hubble-gateway.rpi-imager-manifest` | Local Imager manifest so the Customization wizard appears |
