"""CLI entry point for the Hubble Gateway SDK."""

import argparse
import asyncio
import os
import sys

from hubble_gateway import __version__


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="hubble-gateway",
        description="Hubble Network BLE Gateway — scans for BLE devices and uploads to the Hubble cloud",
    )
    parser.add_argument("--version", action="version", version=f"hubble-gateway {__version__}")
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

    if args.sdk_key:
        os.environ["HUBBLE_SDK_KEY"] = args.sdk_key
    if args.api_url:
        os.environ["HUBBLE_API_BASE_URL"] = args.api_url
    if args.adapter:
        os.environ["HUBBLE_BLE_ADAPTER"] = args.adapter
    if args.gps:
        os.environ["HUBBLE_GPS_ENABLED"] = "true"
    if args.gps_port:
        os.environ["HUBBLE_GPS_PORT"] = args.gps_port
    if args.gps_baud:
        os.environ["HUBBLE_GPS_BAUD_RATE"] = str(args.gps_baud)
    if args.gps_module:
        os.environ["HUBBLE_GPS_MODULE"] = args.gps_module
    if args.lat is not None:
        os.environ["HUBBLE_LATITUDE"] = str(args.lat)
    if args.lon is not None:
        os.environ["HUBBLE_LONGITUDE"] = str(args.lon)
    if args.log_level:
        os.environ["HUBBLE_LOG_LEVEL"] = args.log_level
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

    print(f"Hubble Gateway SDK v{__version__}")
    print(f"  SDK key: {sdk_key[:8]}...{sdk_key[-4:]}")
    print()

    from hubble_gateway.daemon import run
    asyncio.run(run())
