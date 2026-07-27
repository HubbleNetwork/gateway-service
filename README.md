# Hubble Gateway Service

Ready-to-run BLE gateway for [Hubble Network](https://hubblenetwork.com). It
scans for Bluetooth Low Energy devices and uploads sightings to the Hubble
cloud. Built on the [hubble-gateway SDK](https://github.com/HubbleNetwork/gateway-sdk-python).

Pick the path that matches your hardware:

- [**New Raspberry Pi**](#new-raspberry-pi--flash-the-image) — flash a
  ready-to-run SD card. No terminal needed.
- [**Existing Raspberry Pi / Linux**](#existing-raspberry-pi--linux--one-line-install) —
  one-line install onto a machine you already run.

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

3. **Flash it** with Imager and set **Wi‑Fi** in OS Customization (or skip it to
   use ethernet).
4. **Set your SDK key + location.** On the boot partition (`bootfs`), copy
   `hubble-gateway.conf.example` to `hubble-gateway.conf` and edit:

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

## Existing Raspberry Pi / Linux — one-line install

Already have a running Pi or Linux box? Install the gateway as a systemd
service:

```bash
curl -fsSL https://raw.githubusercontent.com/HubbleNetwork/gateway-service/main/scripts/install.sh \
  | sudo bash -s -- --sdk-key <YOUR_SDK_KEY>
```

This downloads a single pre-built binary (no Python required), writes your
config, registers a systemd service, and starts it. It falls back to pip if no
binary is available for your architecture.

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

## Advanced

Full configuration reference (env vars / CLI flags), GPS modules, USB BLE
dongles, manual install (pip, direct binary, systemd unit), and architecture:
**[Advanced configuration](docs/advanced_config.md)**.

## License

Apache License 2.0 — see [LICENSE](LICENSE).
