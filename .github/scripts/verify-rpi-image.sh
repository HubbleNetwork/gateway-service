#!/usr/bin/env bash
# Inspect a built hubble-gateway Raspberry Pi image and fail if anything the
# gateway needs to start on boot is missing.
#
#   verify-rpi-image.sh <path/to/image.img>
#
# Reads the partitions directly (sfdisk + debugfs + mtools), so it needs no
# loop devices, mounts or root. Requires: sfdisk (util-linux), debugfs
# (e2fsprogs), mdir (mtools), dd.
#
# Guards against image-v0.1.3/v0.1.4, which built "successfully" but shipped
# without the layer's overlay (no provisioner, no units, nothing enabled),
# because rpi-image-gen changed where it looks for a layer's overlay and hooks.
set -euo pipefail

IMG="${1:?usage: verify-rpi-image.sh <image.img>}"
[ -f "$IMG" ] || { echo "verify-image: no such file: $IMG" >&2; exit 2; }

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

fail=0
ok()  { printf '  ok    %s\n' "$*"; }
bad() { printf '  FAIL  %s\n' "$*"; fail=1; }

# --- Partitions: 1 = FAT boot, 2 = ext4 root (image-rpios layout) -----------
mapfile -t parts < <(sfdisk -d "$IMG" | sed -n 's/.*start= *\([0-9]*\), *size= *\([0-9]*\).*/\1 \2/p')
if [ "${#parts[@]}" -lt 2 ]; then
    echo "verify-image: expected >=2 partitions in $IMG" >&2
    sfdisk -d "$IMG" >&2 || true
    exit 1
fi
read -r boot_start boot_size <<<"${parts[0]}"
read -r root_start root_size <<<"${parts[1]}"

BOOT="${WORK}/boot.vfat"
ROOT="${WORK}/root.ext4"
dd if="$IMG" of="$BOOT" bs=512 skip="$boot_start" count="$boot_size" status=none
dd if="$IMG" of="$ROOT" bs=512 skip="$root_start" count="$root_size" status=none

# --- Helpers over the ext4 root ---------------------------------------------
dstat() { debugfs -R "stat \"$1\"" "$ROOT" 2>/dev/null || true; }
ftype() { dstat "$1" | sed -n 's/.*Type: \([a-z]*\).*/\1/p' | head -n1; }
fmode() { dstat "$1" | sed -n 's/.*Mode: *\([0-7]*\).*/\1/p' | head -n1; }
flink() { dstat "$1" | sed -n 's/^Fast link dest: "\(.*\)"$/\1/p' | head -n1; }
fcat()  { debugfs -R "cat \"$1\"" "$ROOT" 2>/dev/null || true; }

need_exec() {
    local p="$1" t m
    t="$(ftype "$p")"
    if [ "$t" = symlink ]; then
        local dest; dest="$(flink "$p")"
        case "$dest" in /*) ;; *) dest="$(dirname "$p")/${dest}" ;; esac
        p="$dest"; t="$(ftype "$p")"
    fi
    m="$(fmode "$p")"
    if [ "$t" != regular ]; then
        bad "$1 missing (type='${t:-none}')"
    elif (( (8#${m:-0} & 8#111) == 0 )); then
        bad "$1 not executable (mode ${m})"
    else
        ok "$1 (mode ${m})"
    fi
}

need_file() {
    local t; t="$(ftype "$1")"
    if [ "$t" = regular ]; then ok "$1"; else bad "$1 missing (type='${t:-none}')"; fi
}

need_enabled() {
    local unit="$1" link="/etc/systemd/system/multi-user.target.wants/$1" t dest
    t="$(ftype "$link")"
    dest="$(flink "$link")"
    if [ "$t" = symlink ] && [ "${dest##*/}" = "$unit" ]; then
        ok "$link -> $dest"
    else
        bad "$unit not enabled ($link type='${t:-none}' dest='${dest}')"
    fi
}

echo "verify-image: $IMG"
echo "root partition:"
need_exec    /usr/local/sbin/hubble-provision
need_file    /etc/systemd/system/hubble-provision.service
need_file    /etc/systemd/system/hubble-gateway.service
need_enabled hubble-provision.service
need_enabled hubble-gateway.service
need_exec    /opt/hubble-gateway/hubble-gateway
need_file    /opt/hubble-gateway/.env

echo "boot partition:"
if mdir -b -i "$BOOT" ::/hubble-gateway.conf.example >/dev/null 2>&1; then
    ok "/boot/firmware/hubble-gateway.conf.example"
else
    bad "/boot/firmware/hubble-gateway.conf.example missing from FAT partition"
fi

echo "access hardening:"
user1="$(fcat /etc/passwd | awk -F: '$3 == 1000 {print $1}')"
if [ -z "$user1" ]; then
    bad "no uid 1000 login user in /etc/passwd"
else
    hash="$(fcat /etc/shadow | awk -F: -v u="$user1" '$1 == u {print $2}')"
    case "$hash" in
        '!'*|'*'*) ok "${user1} has no usable password (locked: '${hash:0:1}')" ;;
        *) bad "${user1} has a password baked into the image (shared across every device)" ;;
    esac
fi
if fcat /etc/ssh/sshd_config.d/01pubkey-only.conf | grep -qx 'PasswordAuthentication no'; then
    ok "sshd: PasswordAuthentication no (01pubkey-only.conf)"
else
    bad "sshd password authentication not disabled (01pubkey-only.conf missing)"
fi

if [ "$fail" -ne 0 ]; then
    echo "verify-image: FAILED" >&2
    exit 1
fi
echo "verify-image: all checks passed"
