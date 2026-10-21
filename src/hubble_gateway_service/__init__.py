"""Hubble Network Gateway Service — background daemon powered by hubble-gateway SDK."""

from importlib.metadata import PackageNotFoundError, version

try:
    # Read the installed distribution's version rather than restating it here.
    # A hand-maintained string sat at 0.1.0 across three releases.
    __version__ = version("hubble-gateway-service")
except PackageNotFoundError:  # running from a source tree that was never installed
    __version__ = "0.0.0+unknown"

__all__ = ["__version__"]
