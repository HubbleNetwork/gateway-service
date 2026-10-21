"""The example unit files must match what scripts/install.sh writes."""

import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
INSTALL_SH = ROOT / "scripts" / "install.sh"
EXAMPLES = ROOT / "examples" / "systemd"

CASES = [
    ("hubble-gateway.service", []),
    ("hubble-gateway-pip.service", ["--pip"]),
    ("hubble-gateway-readonly-root.service", ["--install-dir", "/data/hubble-gateway"]),
]


def print_unit(*args: str) -> str:
    result = subprocess.run(
        ["sh", str(INSTALL_SH), "--print-unit", *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout


@pytest.mark.parametrize(("name", "args"), CASES)
def test_example_unit_matches_installer(name: str, args: list[str]) -> None:
    expected = print_unit(*args)
    actual = (EXAMPLES / name).read_text()
    assert actual == expected, (
        f"examples/systemd/{name} is out of date; regenerate it with "
        f"`sh scripts/install.sh --print-unit {' '.join(args)}`"
    )


def test_every_example_is_checked() -> None:
    assert sorted(p.name for p in EXAMPLES.glob("*.service")) == sorted(n for n, _ in CASES)


def test_unit_keeps_writes_under_install_dir() -> None:
    unit = print_unit("--install-dir", "/srv/gw")
    for line in (
        "Environment=XDG_CACHE_HOME=/srv/gw/cache",
        "Environment=XDG_DATA_HOME=/srv/gw/share",
        "Environment=TMPDIR=/srv/gw/tmp",
        "Environment=HUBBLE_AUTH_TOKEN_PATH=/srv/gw/auth.json",
        "EnvironmentFile=/srv/gw/.env",
        "ExecStart=/srv/gw/hubble-gateway",
    ):
        assert line in unit.splitlines()


@pytest.mark.skipif(shutil.which("dash") is None, reason="dash not installed")
def test_script_is_posix_sh() -> None:
    subprocess.run(["dash", "-n", str(INSTALL_SH)], check=True)
