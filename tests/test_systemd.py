import asyncio
import os
import socket
import tempfile

import pytest

from hubble_gateway_service import systemd


@pytest.fixture
def notify_socket(monkeypatch):
    # AF_UNIX paths are limited to ~104 bytes on macOS, so avoid pytest's tmp_path.
    with tempfile.TemporaryDirectory(dir="/tmp") as d:
        path = os.path.join(d, "notify")
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        sock.bind(path)
        sock.settimeout(2)
        monkeypatch.setenv("NOTIFY_SOCKET", path)
        try:
            yield sock
        finally:
            sock.close()


def test_notify_without_socket_is_noop(monkeypatch):
    monkeypatch.delenv("NOTIFY_SOCKET", raising=False)
    assert systemd.notify("WATCHDOG=1") is False


def test_notify_sends_datagram(notify_socket):
    assert systemd.notify("WATCHDOG=1") is True
    assert notify_socket.recv(64) == b"WATCHDOG=1"


@pytest.mark.skipif(not hasattr(socket, "SO_PEERCRED"), reason="abstract sockets are Linux-only")
def test_notify_abstract_socket(monkeypatch):
    name = f"hubble-test-{os.getpid()}"
    with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as sock:
        sock.bind("\0" + name)
        sock.settimeout(2)
        monkeypatch.setenv("NOTIFY_SOCKET", "@" + name)
        assert systemd.notify("WATCHDOG=1") is True
        assert sock.recv(64) == b"WATCHDOG=1"


def test_notify_unreachable_socket_returns_false(monkeypatch):
    monkeypatch.setenv("NOTIFY_SOCKET", "/nonexistent/notify")
    assert systemd.notify("WATCHDOG=1") is False


@pytest.mark.parametrize(
    ("usec", "expected"),
    [
        (None, None),
        ("", None),
        ("junk", None),
        ("0", None),
        ("300000000", 30.0),
        ("30000000", 10.0),
    ],
)
def test_watchdog_interval(monkeypatch, usec, expected):
    if usec is None:
        monkeypatch.delenv("WATCHDOG_USEC", raising=False)
    else:
        monkeypatch.setenv("WATCHDOG_USEC", usec)
    assert systemd.watchdog_interval() == expected


async def test_watchdog_loop_pings_only_while_healthy(monkeypatch, notify_socket):
    monkeypatch.setenv("WATCHDOG_USEC", "150000")  # 50 ms interval
    notify_socket.setblocking(False)
    healthy = True
    shutdown = asyncio.Event()
    task = asyncio.create_task(systemd.watchdog_loop(lambda: healthy, shutdown))

    await asyncio.sleep(0.12)
    assert notify_socket.recv(64) == b"WATCHDOG=1"
    while True:
        try:
            notify_socket.recv(64)
        except BlockingIOError:
            break

    healthy = False
    await asyncio.sleep(0.12)
    with pytest.raises(BlockingIOError):
        notify_socket.recv(64)

    shutdown.set()
    await asyncio.wait_for(task, timeout=1)


async def test_watchdog_loop_returns_when_disabled(monkeypatch):
    monkeypatch.delenv("WATCHDOG_USEC", raising=False)
    await asyncio.wait_for(systemd.watchdog_loop(lambda: True, asyncio.Event()), timeout=1)
