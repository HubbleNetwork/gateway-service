"""The service reports its own version, not the SDK's.

cli.py once reported ``hubble-gateway-service {hubble_gateway.__version__}``,
which is the SDK's version wearing the service's name, and ``__version__`` was
a hand-maintained string that sat at 0.1.0 across three releases.
"""

import sys
from importlib.metadata import version

import hubble_gateway
import pytest

from hubble_gateway_service import __version__
from hubble_gateway_service.cli import main


def test_version_matches_installed_metadata():
    """__version__ must not drift from pyproject, so it is derived, not typed."""
    assert __version__ == version("hubble-gateway-service")


def test_version_flag_leads_with_the_service_version(capsys, monkeypatch):
    monkeypatch.setattr(sys, "argv", ["hubble-gateway", "--version"])

    with pytest.raises(SystemExit) as exc:
        main()

    assert exc.value.code == 0
    assert capsys.readouterr().out.startswith(f"hubble-gateway-service {__version__}")


def test_version_flag_does_not_pass_the_sdk_version_off_as_ours(capsys, monkeypatch):
    """Guards the original bug: these two versions differ in a real release."""
    monkeypatch.setattr(hubble_gateway, "__version__", "9.9.9")
    monkeypatch.setattr(sys, "argv", ["hubble-gateway", "--version"])

    with pytest.raises(SystemExit):
        main()

    out = capsys.readouterr().out
    assert f"hubble-gateway-service {__version__}" in out
    assert "hubble-gateway-service 9.9.9" not in out
