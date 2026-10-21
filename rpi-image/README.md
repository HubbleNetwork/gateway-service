# Hubble Gateway — Raspberry Pi image

A ready-to-flash Raspberry Pi OS image that runs the Hubble Network BLE gateway
automatically on boot. Images are built by CI (see
[Building the image](#building-the-image-maintainers)); as an operator you just
**download a prebuilt image and flash it**.

> [!WARNING]
> **Flash through the manifest, not "Use custom".** If you pick the `.img.xz`
> directly via Imager's **Choose OS → Use custom**, Imager **skips OS
> Customization entirely** — no Wi‑Fi, no SSH key, no hostname — and because
> this image has **no default password** you will have no way to log in. Always
> load `hubble-gateway.rpi-imager-manifest` (step 3) and pick
> **Choose OS → Hubble Gateway**. (If you already flashed via "Use custom", you
> can still add Wi‑Fi and an SSH key through `hubble-gateway.conf`, step 4.)

The flow:

1. **Install Raspberry Pi Imager.**
2. **Download** the image for your Pi model via the direct link below.
3. **Flash** it with Imager **via the manifest** and set **Wi‑Fi** (or leave it
   for ethernet) and your **SSH public key**.
4. **Edit `hubble-gateway.conf`** on the boot partition with your SDK key + location.
5. Boot the Pi — it provisions itself and the gateway starts.

> [!IMPORTANT]
> **There is no default password.** The `hubble` account has a locked password
> and SSH accepts public keys only. You get in with an SSH key supplied in
> Imager's OS Customization or via `SSH_AUTHORIZED_KEY=` in
> `hubble-gateway.conf` — see [Logging in](#logging-in).

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

## 3. Flash with Raspberry Pi Imager (and set Wi‑Fi + SSH key)

> [!WARNING]
> Do **not** use **Choose OS → Use custom** with the `.img.xz`: that path
> **skips OS Customization** (Wi‑Fi, SSH key, hostname, user), and the image has
> no default password. Use the manifest as below.

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
- **SSH** — enable it and choose **public-key authentication**, then
  paste your public key (e.g. the contents of `~/.ssh/id_ed25519.pub`). This is
  how you log in; the image has no default password.
- **Hostname**, **username/password**, **locale** as desired. A password set
  here works on the console and for `sudo`; SSH stays key-only unless you also
  set `SSH_PASSWORD_AUTH=yes` (step 4).

Then **Save** and **Write** the image.

These fields map to Imager's `firstrun.sh`, which this image honors via the
`raspberrypi-sys-mods` package (it configures NetworkManager, SSH and hostname).

> **Why isn't the SDK key a field here?** Imager's customization fields are a
> fixed set (hostname, user, wifi, SSH, locale). Imager has no mechanism for a
> custom "SDK Key" field, so the key is supplied via the boot partition instead
> (next step).

---

## 4. Edit `hubble-gateway.conf` (SDK key + location)

After flashing, **remove the card/USB and re-insert it** — the small
**`bootfs`** (FAT) partition then mounts on your computer containing
**`hubble-gateway.conf.example`**.

1. Copy the example to the real filename and open it for editing:

   ```bash
   cp /Volumes/bootfs/hubble-gateway.conf.example /Volumes/bootfs/hubble-gateway.conf
   nano /Volumes/bootfs/hubble-gateway.conf   # Linux: /media/<you>/bootfs/...
   ```

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
`WIFI_COUNTRY`, `SSH_AUTHORIZED_KEY`, `SSH_PASSWORD_AUTH` (also accepts
`HUBBLE_*` names for the gateway settings).

To authorize an SSH key without Imager (e.g. you flashed via "Use custom"), add
one line per key:

```ini
SSH_AUTHORIZED_KEY=ssh-ed25519 AAAAC3Nza...your-key... you@laptop
```

> The daemon requires a location. Provide `LAT`+`LON` or `GPS=true`. Without a
> location the service starts, fails fast, and retries every 15s until you set
> one.

---

## Logging in

The image ships with **no shared password**: the login account (`hubble`, uid
1000) has a locked password, and sshd allows **public-key authentication only**
(`/etc/ssh/sshd_config.d/01pubkey-only.conf`; root login disabled). The account
has passwordless `sudo`, so the SSH key is the credential that protects the
device. Ways in:

| How | What to do |
|---|---|
| **SSH key via Imager** (recommended) | OS Customization → SSH → public-key only → paste your key. Then `ssh hubble@hubble-gateway.local` (or the username/hostname you set). |
| **SSH key via the boot partition** | Add `SSH_AUTHORIZED_KEY=<your .pub line>` to `hubble-gateway.conf` (repeat for more keys). Applied on next boot for the uid‑1000 user. |
| **Console (HDMI + keyboard / serial)** | Only if you set a username/password in Imager's OS Customization. |
| **Password SSH** (not recommended) | Set a password in Imager *and* add `SSH_PASSWORD_AUTH=yes` to `hubble-gateway.conf`. `SSH_PASSWORD_AUTH=no` turns it back off. |

If Imager renamed the user, `sudo` uses the password you set in Imager.

Lost access? Re-insert the card, add `SSH_AUTHORIZED_KEY=...` to
`hubble-gateway.conf` on the boot partition, and boot again. (Anyone with
physical access to the card can do this, as with any Pi — protect the device
physically.)

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
                                                     ├─► ~/.ssh/authorized_keys (SSH_AUTHORIZED_KEY)
                                                     └─► sshd_config.d (SSH_PASSWORD_AUTH)

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
- **On a tag** `image-v*`: builds all models (`rpi5`, `rpi4`, `rpi3`,
  `zero2w`, `cm4`, `cm5`) and attaches the compressed images to a GitHub
  Release, which becomes the `latest` release the README links point at.

The workflow writes a small `ci.yaml` that `include:`s `hubble-gateway.yaml` and
overrides `device.layer` / `hubble.version` / `hubble.install_method` per run.

**rpi-image-gen is pinned** to a specific commit (`RIG_REF` in the workflow).
Upstream changes its layer layout without notice — image-v0.1.3/v0.1.4 were
built against unpinned `master` after upstream moved per-layer overlays to
`<layer>.d/customize.overlay` and hooks from `bdebstrap/` to `hooks/`, and
shipped without the provisioner or any enabled units. To move to a newer
upstream, run the workflow manually with `rpi_image_gen_ref=<sha>`, check that
**Verify image contents** passes, then update the pinned SHA.

Every build runs `.github/scripts/verify-rpi-image.sh` on the produced `.img`
(reads the partitions with `debugfs`/`mtools`, no mounts) and fails if the
provisioner, the systemd units and their `multi-user.target.wants` links, the
daemon, or `hubble-gateway.conf.example` on the FAT partition are missing, or if
a password is baked in / SSH password auth is on. You can run it locally on any
built or downloaded (decompressed) image.

### Build locally

On a Debian/Ubuntu amd64 host (cross-build) or a Pi:

```bash
git clone https://github.com/raspberrypi/rpi-image-gen.git
cd rpi-image-gen
git checkout a67e556612a1f902245b2dc1b21c476f570e16b5   # the SHA pinned in rpi-image.yml
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
- `ssh.pubkey_user1` — bake an SSH public key (file path or key text) into the
  image for your own fleet builds. Leave empty for published images.
- Do **not** add `device.user1pass` back: it would be a password shared by every
  device flashed from the image (the verify step rejects it).

### What's in this directory

| Path | Purpose |
|---|---|
| `config/hubble-gateway.yaml` | Build config — selects device/image/networking and Hubble options |
| `layer/hubble-gateway.yaml` | Custom layer — installs the daemon, seeds config, checks the overlay landed, enables services |
| `layer/hubble-gateway.d/customize.overlay/` | Files baked into the image (systemd units, provisioner, boot config example); rpi-image-gen applies it just before the layer's customize-hooks |
| `hubble-gateway.rpi-imager-manifest` | Local Imager manifest so the Customization wizard appears |
