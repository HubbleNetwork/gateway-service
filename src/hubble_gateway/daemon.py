"""Main daemon: orchestrates scanner, sender, and location provider."""

import asyncio
import signal
import sys

import structlog

from hubble_gateway import __version__
from hubble_gateway.auth import GatewayAuth
from hubble_gateway.config import Settings
from hubble_gateway.location import create_location_provider
from hubble_gateway.models import BLEPacket
from hubble_gateway.scanner import Scanner
from hubble_gateway.sender import GatewaySender

logger = structlog.get_logger(__name__)


def _configure_logging(settings: Settings) -> None:
    processors = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
    ]
    if settings.log_json:
        processors.append(structlog.processors.JSONRenderer())
    else:
        processors.append(structlog.dev.ConsoleRenderer())

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(structlog, settings.log_level.upper(), structlog.INFO)  # type: ignore[arg-type]
        ),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


async def run() -> None:
    settings = Settings()
    _configure_logging(settings)

    logger.info(
        "Starting Hubble Gateway",
        version=__version__,
        sdk_key=f"{settings.sdk_key[:8]}...",
        api_url=settings.api_base_url,
    )

    if not settings.sdk_key:
        logger.error("SDK key is required")
        sys.exit(1)

    shutdown_event = asyncio.Event()

    def handle_signal(sig: signal.Signals) -> None:
        logger.info("Shutdown signal received", signal=sig.name)
        shutdown_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, handle_signal, sig)

    location_provider = await create_location_provider(
        gps_enabled=settings.gps_enabled,
        fixed_lat=settings.latitude,
        fixed_lon=settings.longitude,
        gps_port=settings.gps_port,
        gps_baud_rate=settings.gps_baud_rate,
        gps_module=settings.gps_module,
    )

    loc = await location_provider.get_location()
    logger.info(
        "Location provider ready",
        source=loc.source,
        lat=loc.latitude,
        lon=loc.longitude,
    )

    auth = GatewayAuth(
        sdk_key=settings.sdk_key,
        base_url=settings.api_base_url,
        token_path=settings.auth_token_path,
    )
    await auth.start()

    if not await auth.ensure_authenticated():
        logger.error("Gateway registration failed — check your SDK key and network connectivity")
        await auth.stop()
        sys.exit(1)

    sender = GatewaySender(
        auth=auth,
        get_location=location_provider.get_location,
        batch_size=settings.batch_size,
        upload_interval_s=settings.upload_interval_seconds,
        dedup_window_s=settings.dedup_window_seconds,
    )
    await sender.start()

    def on_packet(packet: BLEPacket) -> None:
        sender.add_packet(packet)

    scanner = Scanner(
        service_uuids=settings.service_uuids,
        scan_duration=settings.scan_duration_seconds,
        on_packet=on_packet,
        adapter=settings.ble_adapter or None,
    )

    scanner_task = asyncio.create_task(scanner.start())
    heartbeat_task = asyncio.create_task(_heartbeat_loop(auth, shutdown_event))
    stats_task = asyncio.create_task(_stats_loop(sender, scanner, location_provider, shutdown_event))

    logger.info(
        "Gateway running",
        gateway_id=auth.gateway_id,
        adapter=settings.ble_adapter or "default",
        gps=settings.gps_enabled,
    )

    await shutdown_event.wait()

    logger.info("Shutting down...")
    await scanner.stop()
    scanner_task.cancel()
    try:
        await scanner_task
    except asyncio.CancelledError:
        pass
    heartbeat_task.cancel()
    stats_task.cancel()

    await sender.stop()
    await auth.stop()
    await location_provider.stop()
    logger.info("Shutdown complete")


async def _heartbeat_loop(auth: GatewayAuth, shutdown: asyncio.Event) -> None:
    while not shutdown.is_set():
        try:
            await asyncio.wait_for(shutdown.wait(), timeout=300)
            break
        except asyncio.TimeoutError:
            pass
        try:
            await auth.heartbeat()
        except Exception as e:
            logger.warning("Heartbeat failed", error=str(e))


async def _stats_loop(sender, scanner, location_provider, shutdown: asyncio.Event) -> None:
    while not shutdown.is_set():
        try:
            await asyncio.wait_for(shutdown.wait(), timeout=60)
            break
        except asyncio.TimeoutError:
            pass
        loc = await location_provider.get_location()
        logger.info(
            "Status",
            scanner=scanner.stats,
            sender=sender.stats,
            gps_source=loc.source,
            gps_state=loc.gps_state,
            gps_sats=loc.sat_count,
        )
