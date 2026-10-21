#!/bin/sh
# Hubble Gateway — one-line installer for Raspberry Pi / Linux
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/HubbleNetwork/gateway-service/main/scripts/install.sh | sudo sh -s -- --sdk-key <YOUR_KEY>
#
# Options:
#   --sdk-key KEY        SDK key (required)
#   --gps                Enable GPS
#   --gps-port PORT      GPS serial port (default: /dev/ttyAMA0)
#   --gps-baud RATE      GPS baud rate (default: 9600)
#   --gps-module MODULE  nmea or zed_f9p (default: nmea)
#   --adapter ADAPTER    BLE adapter (default: auto)
#   --lat LAT            Fixed latitude
#   --lon LON            Fixed longitude
#   --install-dir DIR    Where to install (default: /opt/hubble-gateway, or a
#                        persistent writable location such as /data when /opt
#                        is read-only)
#   --version TAG        Binary release to install, e.g. v0.1.2 (default: newest)
#   --pip                Force pip install (skip binary)
#   --print-unit         Print the systemd unit this installer writes, then exit
#   --uninstall          Remove the gateway service
#
# Written for POSIX sh so it also runs on BusyBox and Yocto systems without bash.

set -eu

# Everything runs from main, called on the last line, so a download cut off
# partway through `curl | sh` runs nothing instead of half the installer.
main() {

    REPO="HubbleNetwork/gateway-service"
    SERVICE_NAME="hubble-gateway"
    SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"
    DEFAULT_INSTALL_DIR="/opt/hubble-gateway"
    # Tried in order when --install-dir is not given. /opt is the normal case; the
    # rest cover read-only root filesystems (Yocto, OTA A/B images) that keep a
    # writable data partition.
    INSTALL_DIR_CANDIDATES="/opt/hubble-gateway /data/hubble-gateway /persist/hubble-gateway /var/lib/hubble-gateway"

    if [ -t 2 ]; then
        RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
    else
        RED=''; GREEN=''; YELLOW=''; NC=''
    fi

    info()  { printf '%b[hubble]%b %s\n' "${GREEN}" "${NC}" "$*"; }
    warn()  { printf '%b[hubble]%b %s\n' "${YELLOW}" "${NC}" "$*"; }
    error() { printf '%b[hubble]%b %s\n' "${RED}" "${NC}" "$*" >&2; }
    fatal() { error "$@"; exit 1; }

    SDK_KEY=""
    GPS_ENABLED="false"
    GPS_PORT="/dev/ttyAMA0"
    GPS_BAUD="9600"
    GPS_MODULE="nmea"
    BLE_ADAPTER=""
    LATITUDE=""
    LONGITUDE=""
    INSTALL_DIR=""
    BINARY_TAG=""
    UNINSTALL=false
    FORCE_PIP=false
    PRINT_UNIT=false

    need_arg() { [ $# -ge 2 ] || fatal "Missing value for $1"; }

    while [ $# -gt 0 ]; do
        case "$1" in
            --sdk-key)     need_arg "$@"; SDK_KEY="$2"; shift 2 ;;
            --gps)         GPS_ENABLED="true"; shift ;;
            --gps-port)    need_arg "$@"; GPS_PORT="$2"; shift 2 ;;
            --gps-baud)    need_arg "$@"; GPS_BAUD="$2"; shift 2 ;;
            --gps-module)  need_arg "$@"; GPS_MODULE="$2"; shift 2 ;;
            --adapter)     need_arg "$@"; BLE_ADAPTER="$2"; shift 2 ;;
            --lat)         need_arg "$@"; LATITUDE="$2"; shift 2 ;;
            --lon)         need_arg "$@"; LONGITUDE="$2"; shift 2 ;;
            --install-dir) need_arg "$@"; INSTALL_DIR="${2%/}"; shift 2 ;;
            --version)     need_arg "$@"; BINARY_TAG="$2"; shift 2 ;;
            --pip)         FORCE_PIP=true; shift ;;
            --print-unit)  PRINT_UNIT=true; shift ;;
            --uninstall)   UNINSTALL=true; shift ;;
            *)             fatal "Unknown option: $1" ;;
        esac
    done

    # --- systemd unit ---------------------------------------------------------

    # The XDG_*, TMPDIR and token-path settings keep every file the gateway writes
    # inside the install directory. The binary otherwise unpacks its Python
    # runtime under $HOME and the SDK saves its auth tokens there, which fails on a
    # read-only root filesystem. EnvironmentFile is applied after Environment=, so
    # the .env file can still override any of them.
    render_unit() {
        dir="$1"
        exec_path="$2"
        cat <<UNITEOF
[Unit]
Description=Hubble Network BLE Gateway
After=network-online.target bluetooth.target
Wants=network-online.target

[Service]
Type=simple
Environment=XDG_CACHE_HOME=${dir}/cache
Environment=XDG_DATA_HOME=${dir}/share
Environment=TMPDIR=${dir}/tmp
Environment=HUBBLE_AUTH_TOKEN_PATH=${dir}/auth.json
EnvironmentFile=${dir}/.env
ExecStart=${exec_path}
Restart=always
RestartSec=10
WatchdogSec=300
NotifyAccess=all

[Install]
WantedBy=multi-user.target
UNITEOF
    }

    exec_path_for() {
        if [ "$2" = "pip" ]; then
            echo "$1/venv/bin/hubble-gateway"
        else
            echo "$1/hubble-gateway"
        fi
    }

    if $PRINT_UNIT; then
        dir="${INSTALL_DIR:-${DEFAULT_INSTALL_DIR}}"
        if $FORCE_PIP; then method=pip; else method=binary; fi
        render_unit "${dir}" "$(exec_path_for "${dir}" "${method}")"
        exit 0
    fi

    # --- Helpers --------------------------------------------------------------

    have() { command -v "$1" >/dev/null 2>&1; }

    has_systemd() { have systemctl && [ -d /run/systemd/system ]; }

    # Prints "<fstype> <mount options>" for the mount that holds path $1. Plain sh
    # rather than awk, which minimal images (openSUSE, some Yocto) leave out.
    mount_info() {
        real=$(cd "$1" && pwd -P)
        best=-1
        found=""
        while read -r _dev mp fstype opts _rest; do
            if [ "${mp}" = "/" ]; then prefix="/"; else prefix="${mp}/"; fi
            case "${real}/" in
                "${prefix}"*) ;;
                *) continue ;;
            esac
            # ">=" so the last of several mounts on one point (the visible one) wins.
            if [ "${#mp}" -ge "${best}" ]; then
                best=${#mp}
                found="${fstype} ${opts}"
            fi
        done < /proc/mounts
        echo "${found}"
    }

    # True when files under $1 are lost on reboot: tmpfs/ramfs, or an overlay whose
    # writable upper layer is itself on tmpfs (e.g. Yocto's /var/lib on /var/volatile).
    is_volatile() {
        [ -r /proc/mounts ] || return 1
        set -- "$1" "$(mount_info "$1")"
        fstype="${2%% *}"
        case "${fstype}" in
            tmpfs|ramfs) return 0 ;;
            overlay)
                upper=$(printf '%s\n' "${2#* }" | tr ',' '\n' | sed -n 's/^upperdir=//p')
                if [ -n "${upper}" ] && [ -d "${upper}" ]; then
                    case "$(mount_info "${upper}")" in
                        tmpfs*|ramfs*) return 0 ;;
                    esac
                fi
                ;;
        esac
        return 1
    }

    # Usable install dir: creatable, writable, and not wiped on reboot. Removes a
    # directory it created itself when the dir is rejected.
    usable_install_dir() {
        dir="$1"
        created=false
        if [ ! -d "${dir}" ]; then
            mkdir -p "${dir}" 2>/dev/null || return 1
            created=true
        fi
        probe="${dir}/.hubble-write-test.$$"
        if : > "${probe}" 2>/dev/null; then
            rm -f "${probe}"
            if ! is_volatile "${dir}"; then
                return 0
            fi
        fi
        if ${created}; then rmdir "${dir}" 2>/dev/null || true; fi
        return 1
    }

    # Install dir recorded in an existing unit, so a re-install or uninstall finds
    # the gateway wherever the first install put it.
    installed_dir() {
        [ -f "${SERVICE_FILE}" ] || return 0
        sed -n 's|^EnvironmentFile=-\{0,1\}\(.*\)/\.env$|\1|p' "${SERVICE_FILE}" | head -n 1
    }

    pkg_manager() {
        for pm in apt-get dnf yum zypper pacman apk; do
            if have "${pm}"; then echo "${pm}"; return 0; fi
        done
        return 1
    }

    pkg_install() {
        pm=$(pkg_manager) || return 1
        case "${pm}" in
            apt-get) apt-get update -qq && DEBIAN_FRONTEND=noninteractive apt-get install -y -qq "$@" ;;
            dnf)     dnf install -y -q "$@" ;;
            yum)     yum install -y -q "$@" ;;
            zypper)  zypper --non-interactive --quiet install "$@" ;;
            pacman)  pacman -Sy --noconfirm --needed "$@" ;;
            apk)     apk add --no-cache --quiet "$@" ;;
        esac >>"${LOG_FILE}" 2>&1
    }

    find_bluetoothd() {
        if have bluetoothd; then command -v bluetoothd; return 0; fi
        for p in /usr/libexec/bluetooth/bluetoothd /usr/lib/bluetooth/bluetoothd /usr/sbin/bluetoothd; do
            if [ -x "${p}" ]; then echo "${p}"; return 0; fi
        done
        return 1
    }

    # Runs the gateway with the same file layout the service uses.
    run_with_layout() {
        XDG_CACHE_HOME="${INSTALL_DIR}/cache" \
        XDG_DATA_HOME="${INSTALL_DIR}/share" \
        TMPDIR="${INSTALL_DIR}/tmp" \
        PIP_CACHE_DIR="${INSTALL_DIR}/cache/pip" \
        HUBBLE_AUTH_TOKEN_PATH="${INSTALL_DIR}/auth.json" \
            "$@"
    }

    # --- Uninstall -----------------------------------------------------------

    if $UNINSTALL; then
        [ "$(id -u)" -eq 0 ] || fatal "This script must be run as root (use sudo)"
        info "Uninstalling Hubble Gateway..."
        dir="${INSTALL_DIR:-$(installed_dir)}"
        dir="${dir:-${DEFAULT_INSTALL_DIR}}"
        if have systemctl; then
            systemctl stop "${SERVICE_NAME}" 2>/dev/null || true
            systemctl disable "${SERVICE_NAME}" 2>/dev/null || true
        fi
        rm -f "${SERVICE_FILE}"
        if has_systemd; then systemctl daemon-reload; fi
        # Only delete a directory this installer populated, so a mistyped
        # --install-dir cannot remove something else.
        if [ -n "${dir}" ] && [ "${dir}" != "/" ] && [ -f "${dir}/.env" ]; then
            rm -rf "${dir}"
            info "Removed ${dir} and the systemd service"
        else
            info "Removed the systemd service (no installation found at ${dir})"
        fi
        exit 0
    fi

    # --- Validate -------------------------------------------------------------

    [ "$(id -u)" -eq 0 ] || fatal "This script must be run as root (use sudo)"
    [ -n "${SDK_KEY}" ] || fatal "SDK key is required: --sdk-key <KEY>"
    have curl || fatal "curl is required"

    # --- Install directory ----------------------------------------------------

    if [ -n "${INSTALL_DIR}" ]; then
        usable_install_dir "${INSTALL_DIR}" \
            || fatal "${INSTALL_DIR} is not writable, or is wiped on reboot (tmpfs). Choose a persistent writable directory."
    else
        previous=$(installed_dir)
        for dir in ${previous} ${INSTALL_DIR_CANDIDATES}; do
            if usable_install_dir "${dir}"; then INSTALL_DIR="${dir}"; break; fi
        done
        [ -n "${INSTALL_DIR}" ] || fatal "No persistent writable directory found (tried: ${INSTALL_DIR_CANDIDATES}). Pass one with --install-dir <DIR>."
    fi
    [ "${INSTALL_DIR}" = "${DEFAULT_INSTALL_DIR}" ] || info "Installing to ${INSTALL_DIR} (${DEFAULT_INSTALL_DIR} is not writable)"
    mkdir -p "${INSTALL_DIR}/cache" "${INSTALL_DIR}/share" "${INSTALL_DIR}/tmp"
    ENV_FILE="${INSTALL_DIR}/.env"
    LOG_FILE="${INSTALL_DIR}/install.log"
    : > "${LOG_FILE}"

    # --- Bluetooth ------------------------------------------------------------

    if ! find_bluetoothd >/dev/null; then
        info "Installing BlueZ..."
        case "$(pkg_manager || true)" in
            apt-get) pkg_install bluetooth bluez || true ;;
            pacman)  pkg_install bluez bluez-utils || true ;;
            "")      ;;
            *)       pkg_install bluez || true ;;
        esac
    fi
    if find_bluetoothd >/dev/null; then
        if has_systemd && systemctl cat bluetooth.service >/dev/null 2>&1 \
            && ! systemctl is-active --quiet bluetooth; then
            systemctl enable --now bluetooth || warn "Could not start bluetooth.service"
        fi
    elif pkg_manager >/dev/null; then
        warn "BlueZ (bluetoothd) could not be installed; see ${LOG_FILE}."
        warn "The gateway needs BlueZ to scan. Install it, then restart the gateway."
    else
        warn "BlueZ (bluetoothd) was not found and no supported package manager is available."
        warn "The gateway needs BlueZ to scan. Add it to your system image (e.g. bluez5 on Yocto)."
    fi

    # --- Install: binary (preferred) or pip (fallback) ------------------------

    INSTALLED_VIA=""
    EXEC_PATH=""

    case "$(uname -m)" in
        aarch64|arm64) BINARY_NAME="hubble-gateway-aarch64-linux" ;;
        x86_64|amd64)  BINARY_NAME="hubble-gateway-x86_64-linux" ;;
        *)             BINARY_NAME="" ;;
    esac

    # The release binaries are built against glibc and do not start on musl.
    if [ -n "${BINARY_NAME}" ] && ls /lib/ld-musl-* >/dev/null 2>&1; then
        info "musl libc detected; the pre-built binary needs glibc"
        BINARY_NAME=""
    fi

    if ! $FORCE_PIP && [ -n "${BINARY_NAME}" ]; then
        if [ -z "${BINARY_TAG}" ]; then
            # GitHub's "latest" release is always an image-v* release, which
            # carries no binaries, so resolve the newest v* tag instead.
            BINARY_TAG=$(curl -fsSL "https://api.github.com/repos/${REPO}/releases" 2>/dev/null \
                | grep -o '"tag_name": *"v[^"]*"' | head -n 1 | cut -d'"' -f4 || true)
        fi
        BIN_PATH=$(exec_path_for "${INSTALL_DIR}" binary)
        DOWNLOAD_URL="https://github.com/${REPO}/releases/download/${BINARY_TAG}/${BINARY_NAME}"
        info "Downloading ${BINARY_NAME} ${BINARY_TAG}..."
        if [ -n "${BINARY_TAG}" ] && curl -fsSL "${DOWNLOAD_URL}" -o "${BIN_PATH}.tmp" 2>>"${LOG_FILE}"; then
            chmod +x "${BIN_PATH}.tmp"
            mv -f "${BIN_PATH}.tmp" "${BIN_PATH}"
            # The first run unpacks Python and installs dependencies from PyPI.
            # Doing it here surfaces network or libc problems now, instead of as
            # a restart loop in the service.
            info "Unpacking runtime (first run; needs internet access, ~200 MB)..."
            if run_with_layout "${BIN_PATH}" --version >>"${LOG_FILE}" 2>&1; then
                INSTALLED_VIA="binary"
                EXEC_PATH="${BIN_PATH}"
                info "Installed binary to ${BIN_PATH}"
            else
                warn "The binary failed to start; last lines of ${LOG_FILE}:"
                tail -n 5 "${LOG_FILE}" >&2
                rm -f "${BIN_PATH}"
                warn "Falling back to pip install"
            fi
        else
            rm -f "${BIN_PATH}.tmp"
            warn "Binary not available, falling back to pip install"
        fi
    fi

    python_ok() {
        have python3 && python3 -c 'import sys, venv, ensurepip; sys.exit(sys.version_info < (3, 10))' 2>/dev/null
    }

    if [ -z "${INSTALLED_VIA}" ]; then
        info "Installing via pip..."
        if ! python_ok; then
            case "$(pkg_manager || true)" in
                apt-get) pkg_install python3 python3-venv python3-dev libglib2.0-dev || true ;;
                pacman)  pkg_install python || true ;;
                "")      ;;
                *)       pkg_install python3 || true ;;
            esac
        fi
        python_ok || fatal "pip install needs Python 3.10+ with venv, and none could be installed. See docs/advanced_config.md#manual-install."
        VENV_DIR="${INSTALL_DIR}/venv"
        run_with_layout python3 -m venv "${VENV_DIR}" >>"${LOG_FILE}" 2>&1
        run_with_layout "${VENV_DIR}/bin/pip" install --quiet --upgrade pip >>"${LOG_FILE}" 2>&1 \
            || fatal "pip upgrade failed; see ${LOG_FILE}"
        run_with_layout "${VENV_DIR}/bin/pip" install --quiet hubble-gateway-service >>"${LOG_FILE}" 2>&1 \
            || fatal "pip install failed; see ${LOG_FILE}"
        INSTALLED_VIA="pip"
        EXEC_PATH=$(exec_path_for "${INSTALL_DIR}" pip)
        info "Installed via pip to ${VENV_DIR}"
    fi

    # --- Environment file -----------------------------------------------------

    info "Writing config to ${ENV_FILE}..."
    (
        umask 077
        {
            echo "HUBBLE_SDK_KEY=${SDK_KEY}"
            echo "HUBBLE_GPS_ENABLED=${GPS_ENABLED}"
            echo "HUBBLE_GPS_PORT=${GPS_PORT}"
            echo "HUBBLE_GPS_BAUD_RATE=${GPS_BAUD}"
            echo "HUBBLE_GPS_MODULE=${GPS_MODULE}"
            if [ -n "${BLE_ADAPTER}" ]; then echo "HUBBLE_BLE_ADAPTER=${BLE_ADAPTER}"; fi
            if [ -n "${LATITUDE}" ];    then echo "HUBBLE_LATITUDE=${LATITUDE}"; fi
            if [ -n "${LONGITUDE}" ];   then echo "HUBBLE_LONGITUDE=${LONGITUDE}"; fi
        } > "${ENV_FILE}"
    )
    chmod 600 "${ENV_FILE}"

    # Earlier installers left the SDK's tokens in root's home. Carry them over so
    # the gateway keeps its identity instead of registering again.
    for old in "${HOME:-/root}/.hubble-gateway/auth.json" /root/.hubble-gateway/auth.json; do
        if [ -f "${old}" ] && [ ! -f "${INSTALL_DIR}/auth.json" ]; then
            cp -p "${old}" "${INSTALL_DIR}/auth.json"
            info "Kept existing gateway credentials from ${old}"
        fi
    done

    # --- Service --------------------------------------------------------------

    if ! has_systemd; then
        info ""
        info "Installed (via ${INSTALLED_VIA}), but systemd is not running, so no service was created."
        info "Start the gateway from your init system with:"
        info ""
        info "  set -a; . ${ENV_FILE}; set +a"
        info "  XDG_CACHE_HOME=${INSTALL_DIR}/cache XDG_DATA_HOME=${INSTALL_DIR}/share \\"
        info "  TMPDIR=${INSTALL_DIR}/tmp HUBBLE_AUTH_TOKEN_PATH=${INSTALL_DIR}/auth.json \\"
        info "  ${EXEC_PATH}"
        info ""
        exit 0
    fi

    info "Creating systemd service..."
    mkdir -p "$(dirname "${SERVICE_FILE}")"
    render_unit "${INSTALL_DIR}" "${EXEC_PATH}" > "${SERVICE_FILE}.tmp" \
        || fatal "Cannot write ${SERVICE_FILE}; /etc must be writable to register the service"
    mv -f "${SERVICE_FILE}.tmp" "${SERVICE_FILE}"

    systemctl daemon-reload
    systemctl enable "${SERVICE_NAME}"
    systemctl restart "${SERVICE_NAME}"

    # --- Done -----------------------------------------------------------------

    info ""
    info "Hubble Gateway is running! (installed via ${INSTALLED_VIA})"
    info ""
    info "  Status:  sudo systemctl status ${SERVICE_NAME}"
    info "  Logs:    sudo journalctl -u ${SERVICE_NAME} -f"
    info "  Config:  ${ENV_FILE}"
    info "  Stop:    sudo systemctl stop ${SERVICE_NAME}"
    info "  Remove:  curl -fsSL ... | sudo sh -s -- --uninstall"
    info ""
}

main "$@"
