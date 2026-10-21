# Hubble Gateway Service

Ready-to-run BLE gateway for [Hubble Network](https://hubblenetwork.com). It
scans for Bluetooth Low Energy devices and uploads sightings to the Hubble
cloud. Built on the [hubble-gateway SDK](https://github.com/HubbleNetwork/gateway-sdk-python).

Two things before you start: an **SDK key** from the Hubble dashboard, and a
**location** for the gateway — either fixed coordinates or a GPS module.

## Choose your path

| Your hardware | Start here |
|---|---|
| A new Raspberry Pi | [Flash the image](#new-raspberry-pi--flash-the-image) — no terminal needed |
| A Raspberry Pi or Linux machine you already run | [One-line install](#existing-linux-machine--one-line-install) |
| An embedded image — Yocto, read-only root, no package manager | [Embedded install](#embedded-linux--yocto-and-read-only-images) |

## New Raspberry Pi — flash the image

Flash an SD card with the gateway image; it runs automatically on boot.

1. **Install Raspberry Pi Imager** from
   <https://www.raspberrypi.com/software/>.
2. **Download the image** for your model:

   | Model | Image |
   |---|---|
   | Pi 5 | <https://github.com/HubbleNetwork/gateway-service/releases/latest/download/hubble-gateway-rpi5.img.xz> |
   | Pi 4 | <https://github.com/HubbleNetwork/gateway-service/releases/latest/download/hubble-gateway-rpi4.img.xz> |
   | Pi 3 | <https://github.com/HubbleNetwork/gateway-service/releases/latest/download/hubble-gateway-rpi3.img.xz> |
   | Zero 2 W | <https://github.com/HubbleNetwork/gateway-service/releases/latest/download/hubble-gateway-zero2w.img.xz> |
   | CM4 | <https://github.com/HubbleNetwork/gateway-service/releases/latest/download/hubble-gateway-cm4.img.xz> |
   | CM5 | <https://github.com/HubbleNetwork/gateway-service/releases/latest/download/hubble-gateway-cm5.img.xz> |

3. **Flash it** with Imager **using `rpi-image/hubble-gateway.rpi-imager-manifest`**
   (App Options → Content Repository → Use custom → the manifest; see the
   [image guide](rpi-image/README.md#3-flash-with-raspberry-pi-imager-and-set-wifi--ssh-key)),
   and in OS Customization set **Wi‑Fi** (or skip it for ethernet) and your
   **SSH public key**.

   > **Warning:** choosing the `.img.xz` itself via **Choose OS → Use custom**
   > skips OS Customization. The image has **no default password** — log in
   > with an SSH key (from Imager, or `SSH_AUTHORIZED_KEY=` in
   > `hubble-gateway.conf`).
4. **Set your SDK key + location.** After flashing, **remove the card and
   re-insert it** so the `bootfs` (BOOT) volume mounts on your computer. Copy
   the example config to the real filename and edit it:

   ```bash
   cp /Volumes/bootfs/hubble-gateway.conf.example /Volumes/bootfs/hubble-gateway.conf
   nano /Volumes/bootfs/hubble-gateway.conf   # Linux: /media/<you>/bootfs/...
   ```

   Set at least your SDK key and a location:

   ```ini
   SDK_KEY=hsk_your_key_here
   LAT=37.7749
   LON=-122.4194
   # or, instead of LAT/LON, read it from a GPS module:
   # GPS=true
   ```

5. **Boot the Pi.** It provisions itself and the gateway starts automatically.

Full walkthrough (Imager customization wizard, GPS, verifying on-device):
**[Raspberry Pi image guide](rpi-image/README.md)**.

## Existing Linux machine — one-line install

Already have a Raspberry Pi or Linux box running? Install the gateway as a
systemd service:

```bash
curl -fsSL https://raw.githubusercontent.com/HubbleNetwork/gateway-service/main/scripts/install.sh \
  | sudo sh -s -- --sdk-key <YOUR_SDK_KEY> --lat 37.7749 --lon -122.4194
```

That downloads a single pre-built binary (no Python needed), writes your config
to `/opt/hubble-gateway/.env`, and starts a service that comes back up on
reboot. It works on Debian and Ubuntu, Fedora, openSUSE, Arch and Alpine.

Give it a location, either fixed coordinates as above or a GPS module:

```bash
curl -fsSL https://raw.githubusercontent.com/HubbleNetwork/gateway-service/main/scripts/install.sh \
  | sudo sh -s -- --sdk-key <YOUR_SDK_KEY> --gps --gps-port /dev/ttyAMA0
```

To remove it again:

```bash
curl -fsSL https://raw.githubusercontent.com/HubbleNetwork/gateway-service/main/scripts/install.sh \
  | sudo sh -s -- --uninstall
```

## Embedded Linux — Yocto and read-only images

The same installer handles images that aren't shaped like Debian. It's plain
POSIX `sh`, so it runs under BusyBox without bash, and it works out the rest on
its own:

- **No `apt-get`?** It uses whichever package manager is present — `dnf`,
  `yum`, `zypper`, `pacman` or `apk` — to install BlueZ. With no package
  manager at all, it checks BlueZ is already in the image and tells you if it
  isn't.
- **Read-only root?** `/opt` isn't writable, so it installs to a persistent
  writable partition instead (`/data`, `/persist` or `/var/lib`) and keeps
  everything it writes — Python runtime, cache, auth tokens — inside that
  directory rather than under `$HOME`.
- **No systemd?** It installs the gateway and prints the command to start it.

Choose the install location yourself with `--install-dir`:

```bash
curl -fsSL https://raw.githubusercontent.com/HubbleNetwork/gateway-service/main/scripts/install.sh \
  | sudo sh -s -- --sdk-key <YOUR_SDK_KEY> --lat 37.7749 --lon -122.4194 \
    --install-dir /data/hubble-gateway
```

Two limits worth knowing before you build this into an image. The pre-built
binary needs **glibc 2.34 or newer** — on musl systems such as Alpine the
installer falls back to pip — and on its **first run it downloads its Python
dependencies**, so the device needs internet access once. After that it starts
instantly and runs offline.

The details — the paths it moves off `$HOME`, every installer option, and
ready-made systemd units you can bake into an image — are in
**[Read-only root filesystems](docs/advanced_config.md#read-only-root-filesystems)**.

## Check it's working

```bash
sudo systemctl status hubble-gateway     # should say: active (running)
sudo journalctl -u hubble-gateway -f     # watch it scan and upload
```

Within a minute or two the gateway shows up in your Hubble dashboard. If the
service keeps restarting, the logs almost always name the reason — a missing
location and a bad SDK key are the two common ones.

## Advanced

Full configuration reference (env vars / CLI flags), GPS modules, USB BLE
dongles, manual install (pip, direct binary, systemd unit), and architecture:
**[Advanced configuration](docs/advanced_config.md)**.

## License

Apache License 2.0 — see [LICENSE](LICENSE).
