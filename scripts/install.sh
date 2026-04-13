#!/usr/bin/env bash
# Hubble Gateway SDK — one-line installer for Raspberry Pi
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/HubbleNetwork/gateway-sdk-python/main/scripts/install.sh | sudo bash -s -- --sdk-key <YOUR_KEY>
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
#   --uninstall          Remove the gateway service and venv

set -euo pipefail

INSTALL_DIR="/opt/hubble-gateway"
VENV_DIR="${INSTALL_DIR}/venv"
SERVICE_NAME="hubble-gateway"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"
ENV_FILE="${INSTALL_DIR}/.env"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

info()  { echo -e "${GREEN}[hubble]${NC} $*"; }
warn()  { echo -e "${YELLOW}[hubble]${NC} $*"; }
error() { echo -e "${RED}[hubble]${NC} $*" >&2; }
fatal() { error "$@"; exit 1; }

SDK_KEY=""
GPS_ENABLED="false"
GPS_PORT="/dev/ttyAMA0"
GPS_BAUD="9600"
GPS_MODULE="nmea"
BLE_ADAPTER=""
LATITUDE=""
LONGITUDE=""
UNINSTALL=false

while [[ $# -gt 0 ]]; do
    case "$1" in
        --sdk-key)    SDK_KEY="$2"; shift 2 ;;
        --gps)        GPS_ENABLED="true"; shift ;;
        --gps-port)   GPS_PORT="$2"; shift 2 ;;
        --gps-baud)   GPS_BAUD="$2"; shift 2 ;;
        --gps-module) GPS_MODULE="$2"; shift 2 ;;
        --adapter)    BLE_ADAPTER="$2"; shift 2 ;;
        --lat)        LATITUDE="$2"; shift 2 ;;
        --lon)        LONGITUDE="$2"; shift 2 ;;
        --uninstall)  UNINSTALL=true; shift ;;
        *)            fatal "Unknown option: $1" ;;
    esac
done

# --- Uninstall -----------------------------------------------------------

if $UNINSTALL; then
    info "Uninstalling Hubble Gateway..."
    systemctl stop "${SERVICE_NAME}" 2>/dev/null || true
    systemctl disable "${SERVICE_NAME}" 2>/dev/null || true
    rm -f "${SERVICE_FILE}"
    systemctl daemon-reload
    rm -rf "${INSTALL_DIR}"
    info "Removed ${INSTALL_DIR} and systemd service"
    exit 0
fi

# --- Validate -------------------------------------------------------------

[[ $(id -u) -eq 0 ]] || fatal "This script must be run as root (use sudo)"
[[ -n "${SDK_KEY}" ]] || fatal "SDK key is required: --sdk-key <KEY>"

# --- System dependencies --------------------------------------------------

info "Installing system dependencies..."
apt-get update -qq
apt-get install -y -qq python3 python3-venv python3-dev bluetooth bluez libglib2.0-dev > /dev/null

if ! systemctl is-active --quiet bluetooth; then
    systemctl enable --now bluetooth
fi

# --- Python venv + package ------------------------------------------------

info "Creating virtual environment at ${VENV_DIR}..."
mkdir -p "${INSTALL_DIR}"
python3 -m venv "${VENV_DIR}"

info "Installing hubble-gateway-service..."
"${VENV_DIR}/bin/pip" install --quiet --upgrade pip
"${VENV_DIR}/bin/pip" install --quiet hubble-gateway-service

VERSION=$("${VENV_DIR}/bin/hubble-gateway" --version | awk '{print $2}')
info "Installed hubble-gateway ${VERSION}"

# --- Environment file -----------------------------------------------------

info "Writing config to ${ENV_FILE}..."
cat > "${ENV_FILE}" <<ENVEOF
HUBBLE_SDK_KEY=${SDK_KEY}
HUBBLE_GPS_ENABLED=${GPS_ENABLED}
HUBBLE_GPS_PORT=${GPS_PORT}
HUBBLE_GPS_BAUD_RATE=${GPS_BAUD}
HUBBLE_GPS_MODULE=${GPS_MODULE}
ENVEOF

[[ -n "${BLE_ADAPTER}" ]] && echo "HUBBLE_BLE_ADAPTER=${BLE_ADAPTER}" >> "${ENV_FILE}"
[[ -n "${LATITUDE}" ]]     && echo "HUBBLE_LATITUDE=${LATITUDE}" >> "${ENV_FILE}"
[[ -n "${LONGITUDE}" ]]    && echo "HUBBLE_LONGITUDE=${LONGITUDE}" >> "${ENV_FILE}"

chmod 600 "${ENV_FILE}"

# --- systemd unit ---------------------------------------------------------

info "Creating systemd service..."
cat > "${SERVICE_FILE}" <<UNITEOF
[Unit]
Description=Hubble Network BLE Gateway
After=network-online.target bluetooth.target
Wants=network-online.target

[Service]
Type=simple
EnvironmentFile=${ENV_FILE}
ExecStart=${VENV_DIR}/bin/hubble-gateway
Restart=always
RestartSec=10
WatchdogSec=300

[Install]
WantedBy=multi-user.target
UNITEOF

systemctl daemon-reload
systemctl enable --now "${SERVICE_NAME}"

# --- Done -----------------------------------------------------------------

info ""
info "Hubble Gateway is running!"
info ""
info "  Status:  sudo systemctl status ${SERVICE_NAME}"
info "  Logs:    sudo journalctl -u ${SERVICE_NAME} -f"
info "  Config:  ${ENV_FILE}"
info "  Stop:    sudo systemctl stop ${SERVICE_NAME}"
info "  Remove:  curl -fsSL ... | sudo bash -s -- --uninstall"
info ""
