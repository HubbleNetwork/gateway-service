"""CLI entry point for the Hubble Gateway Service."""

import argparse
import asyncio
import os
import sys

import hubble_gateway


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="hubble-gateway",
        description="Hubble Network BLE Gateway — scans for BLE devices and uploads to the Hubble cloud",
    )
    parser.add_argument(
        "--version", action="version",
        version=f"hubble-gateway-service {hubble_gateway.__version__}",
    )
    parser.add_argument("--sdk-key", help="SDK key (or set HUBBLE_SDK_KEY env var)")
    parser.add_argument("--api-url", help="Gateway API base URL")
    parser.add_argument("--adapter", help="BLE adapter (e.g. hci1 for USB dongle)")
    parser.add_argument("--gps", action="store_true", help="Enable GPS")
    parser.add_argument("--gps-port", help="GPS serial port")
    parser.add_argument("--gps-baud", type=int, help="GPS baud rate")
    parser.add_argument("--gps-module", choices=["nmea", "zed_f9p"], help="GPS module type")
    parser.add_argument("--lat", type=float, help="Fixed latitude")
    parser.add_argument("--lon", type=float, help="Fixed longitude")
    parser.add_argument("--log-level", choices=["DEBUG", "INFO", "WARNING", "ERROR"], default=None)
    parser.add_argument("--log-text", action="store_true", help="Human-readable logs (not JSON)")

    args = parser.parse_args()

    env_map = {
        "sdk_key": "HUBBLE_SDK_KEY",
        "api_url": "HUBBLE_API_BASE_URL",
        "adapter": "HUBBLE_BLE_ADAPTER",
        "gps_port": "HUBBLE_GPS_PORT",
        "gps_module": "HUBBLE_GPS_MODULE",
        "log_level": "HUBBLE_LOG_LEVEL",
    }
    for attr, env_var in env_map.items():
        val = getattr(args, attr, None)
        if val is not None:
            os.environ[env_var] = str(val)

    if args.gps:
        os.environ["HUBBLE_GPS_ENABLED"] = "true"
    if args.gps_baud:
        os.environ["HUBBLE_GPS_BAUD_RATE"] = str(args.gps_baud)
    if args.lat is not None:
        os.environ["HUBBLE_LATITUDE"] = str(args.lat)
    if args.lon is not None:
        os.environ["HUBBLE_LONGITUDE"] = str(args.lon)
    if args.log_text:
        os.environ["HUBBLE_LOG_JSON"] = "false"

    sdk_key = os.environ.get("HUBBLE_SDK_KEY", "")
    if not sdk_key:
        print(
            "Error: SDK key is required.\n"
            "  Pass --sdk-key <key> or set HUBBLE_SDK_KEY environment variable.\n"
            "  Get your key at https://dashboard.hubble.com",
            file=sys.stderr,
        )
        sys.exit(1)

    print(f"Hubble Gateway Service (SDK v{hubble_gateway.__version__})")
    print(f"  SDK key: {sdk_key[:8]}...{sdk_key[-4:]}")
    print()

    from hubble_gateway_service.daemon import run

    asyncio.run(run())
