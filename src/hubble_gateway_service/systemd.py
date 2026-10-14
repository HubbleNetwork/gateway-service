"""Minimal sd_notify client (no libsystemd dependency)."""

import asyncio
import os
import socket
from typing import Callable

import structlog

logger = structlog.get_logger(__name__)

MAX_WATCHDOG_PING_INTERVAL_S = 30.0


def notify(state: str) -> bool:
    """Send a state string such as ``WATCHDOG=1`` to systemd.

    Returns False without error when not running under systemd.
    """
    addr = os.environ.get("NOTIFY_SOCKET")
    if not addr:
        return False
    if addr[0] == "@":
        addr = "\0" + addr[1:]
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as sock:
            sock.connect(addr)
            sock.sendall(state.encode())
    except OSError as e:
        logger.warning("sd_notify failed", state=state, error=str(e))
        return False
    return True


def watchdog_interval() -> float | None:
    """Ping interval in seconds, or None when systemd expects no pings."""
    usec = os.environ.get("WATCHDOG_USEC")
    if not usec:
        return None
    try:
        timeout_s = int(usec) / 1_000_000
    except ValueError:
        return None
    if timeout_s <= 0:
        return None
    return min(MAX_WATCHDOG_PING_INTERVAL_S, timeout_s / 3)


async def watchdog_loop(is_healthy: Callable[[], bool], shutdown: asyncio.Event) -> None:
    """Ping the systemd watchdog while ``is_healthy()`` holds.

    Runs on the event loop, so a blocked loop also stops the pings and lets
    systemd restart the service.
    """
    interval = watchdog_interval()
    if interval is None:
        return
    while not shutdown.is_set():
        if is_healthy():
            notify("WATCHDOG=1")
        else:
            logger.error("Unhealthy; withholding systemd watchdog ping")
        try:
            await asyncio.wait_for(shutdown.wait(), timeout=interval)
        except asyncio.TimeoutError:
            pass
