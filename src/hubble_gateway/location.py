"""Location providers: fixed, serial NMEA GPS, UBX (ZED-F9P), gpsd."""

from __future__ import annotations

import asyncio
import os
import platform
from abc import ABC, abstractmethod

import structlog

from hubble_gateway.models import Location

logger = structlog.get_logger(__name__)


def parse_nmea_coordinate(value: str, direction: str) -> float | None:
    """Parse NMEA coordinate (DDMM.MMMMM or DDDMM.MMMMM) to decimal degrees."""
    if not value or not direction:
        return None
    try:
        dot_pos = value.find(".")
        if dot_pos < 2:
            return None
        deg_digits = 3 if len(value.split(".")[0]) > 4 else 2
        degrees = float(value[:deg_digits])
        minutes = float(value[deg_digits:])
        decimal = degrees + (minutes / 60.0)
        if direction in ("S", "W"):
            decimal = -decimal
        return decimal
    except (ValueError, IndexError):
        return None


class LocationProvider(ABC):
    """Abstract base class for location providers."""

    @abstractmethod
    async def get_location(self) -> Location: ...

    @abstractmethod
    async def start(self) -> None: ...

    @abstractmethod
    async def stop(self) -> None: ...


class FixedLocationProvider(LocationProvider):
    """Returns a static configured location."""

    def __init__(self, latitude: float | None, longitude: float | None) -> None:
        self._location = Location(
            latitude=latitude,
            longitude=longitude,
            source="fixed" if latitude and longitude else "unknown",
        )

    async def get_location(self) -> Location:
        return self._location

    async def start(self) -> None:
        logger.info(
            "Fixed location provider",
            lat=self._location.latitude,
            lon=self._location.longitude,
        )

    async def stop(self) -> None:
        pass


class GPSKalmanFilter:
    """Simple 2D Kalman filter for GPS position smoothing."""

    def __init__(
        self,
        process_noise: float = 1e-10,
        measurement_noise: float = 2e-8,
    ) -> None:
        self._process_noise = process_noise
        self._measurement_noise = measurement_noise
        self._state_lat: float | None = None
        self._state_lon: float | None = None
        self._p_lat: float = 1.0
        self._p_lon: float = 1.0

    def update(self, lat: float, lon: float) -> tuple[float, float]:
        if self._state_lat is None or self._state_lon is None:
            self._state_lat = lat
            self._state_lon = lon
            return lat, lon

        self._p_lat += self._process_noise
        self._p_lon += self._process_noise

        k_lat = self._p_lat / (self._p_lat + self._measurement_noise)
        k_lon = self._p_lon / (self._p_lon + self._measurement_noise)

        self._state_lat = self._state_lat + k_lat * (lat - self._state_lat)
        self._state_lon = self._state_lon + k_lon * (lon - self._state_lon)

        self._p_lat = (1 - k_lat) * self._p_lat
        self._p_lon = (1 - k_lon) * self._p_lon

        return self._state_lat, self._state_lon


class SerialGPSLocationProvider(LocationProvider):
    """Reads NMEA sentences from a serial GPS with Kalman filtering.

    Supports common Pi GPS hats that output GPRMC/GPGGA over a UART serial port.
    """

    def __init__(
        self,
        port: str = "/dev/ttyAMA0",
        baud_rate: int = 9600,
        fallback_lat: float | None = None,
        fallback_lon: float | None = None,
    ) -> None:
        self._port = port
        self._baud_rate = baud_rate
        self._fallback_lat = fallback_lat
        self._fallback_lon = fallback_lon
        self._location = Location(
            latitude=fallback_lat,
            longitude=fallback_lon,
            source="gps-fallback" if fallback_lat else "unknown",
            gps_state="off",
        )
        self._running = False
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._fix_count = 0
        self._kalman = GPSKalmanFilter()
        self._hdop: float | None = None
        self._altitude: float | None = None
        self._sat_count: int | None = None
        self._speed_ms: float | None = None
        self._course_deg: float | None = None

        if fallback_lat is not None and fallback_lon is not None:
            self._kalman.update(fallback_lat, fallback_lon)

    async def get_location(self) -> Location:
        return self._location

    async def start(self) -> None:
        import serial_asyncio

        self._reader, self._writer = await serial_asyncio.open_serial_connection(
            url=self._port, baudrate=self._baud_rate,
        )
        self._running = True
        self._location.gps_state = "searching"
        logger.info("Serial GPS started", port=self._port, baud=self._baud_rate)
        asyncio.create_task(self._read_loop())

    async def _read_loop(self) -> None:
        while self._running and self._reader:
            try:
                line = await asyncio.wait_for(self._reader.readline(), timeout=5.0)
                sentence = line.decode("ascii", errors="ignore").strip()
                if sentence.startswith(("$GPGGA", "$GNGGA")):
                    self._parse_gga(sentence)
                elif sentence.startswith(("$GPRMC", "$GNRMC")):
                    self._parse_rmc(sentence)
            except asyncio.TimeoutError:
                logger.debug("GPS read timeout")
            except Exception as e:
                logger.warning("GPS read error", error=str(e))
                await asyncio.sleep(0.1)

    def _parse_gga(self, sentence: str) -> None:
        try:
            if "*" in sentence:
                sentence = sentence.split("*")[0]
            parts = sentence.split(",")
            if len(parts) < 10:
                return
            quality = int(parts[6]) if parts[6] else 0
            if quality == 0:
                return
            self._sat_count = int(parts[7]) if parts[7] else None
            self._hdop = float(parts[8]) if parts[8] else None
            self._altitude = float(parts[9]) if parts[9] else None
        except (ValueError, IndexError):
            pass

    def _parse_rmc(self, sentence: str) -> None:
        try:
            if "*" in sentence:
                sentence = sentence.split("*")[0]
            parts = sentence.split(",")
            if len(parts) < 7 or parts[2] != "A":
                return
            lat = parse_nmea_coordinate(parts[3], parts[4])
            lon = parse_nmea_coordinate(parts[5], parts[6])
            if len(parts) > 7 and parts[7]:
                self._speed_ms = float(parts[7]) * 0.514444
            if len(parts) > 8 and parts[8]:
                self._course_deg = float(parts[8])
            if lat is not None and lon is not None:
                filtered_lat, filtered_lon = self._kalman.update(lat, lon)
                self._fix_count += 1
                self._location = Location(
                    latitude=filtered_lat,
                    longitude=filtered_lon,
                    altitude=self._altitude,
                    source="gps",
                    gps_state="fix",
                    fix_count=self._fix_count,
                    hdop=self._hdop,
                    sat_count=self._sat_count,
                    speed_ms=self._speed_ms,
                    course_deg=self._course_deg,
                )
                if self._fix_count <= 5 or self._fix_count % 60 == 0:
                    logger.info(
                        "GPS fix",
                        fix=self._fix_count,
                        lat=round(filtered_lat, 6),
                        lon=round(filtered_lon, 6),
                        sats=self._sat_count,
                        hdop=self._hdop,
                    )
        except Exception as e:
            logger.warning("Failed to parse RMC", error=str(e))

    async def stop(self) -> None:
        self._running = False
        if self._writer:
            self._writer.close()
        logger.info("Serial GPS stopped", fixes=self._fix_count)


class UBXLocationProvider(LocationProvider):
    """Reads UBX NAV-PVT from a u-blox receiver (ZED-F9P, NEO-M9N)."""

    def __init__(
        self,
        port: str,
        baud_rate: int = 38400,
        fallback_lat: float | None = None,
        fallback_lon: float | None = None,
        poll_interval_s: float = 1.0,
    ) -> None:
        self._port = port
        self._baud_rate = baud_rate
        self._fallback_lat = fallback_lat
        self._fallback_lon = fallback_lon
        self._poll_interval = poll_interval_s
        self._reader = None
        self._running = False
        self._fix_count = 0
        self._location = Location(
            latitude=fallback_lat,
            longitude=fallback_lon,
            source="gps-fallback" if fallback_lat else "unknown",
            gps_state="off",
        )

    async def start(self) -> None:
        from hubble_gateway.ubx import UBXReader

        self._reader = UBXReader(port=self._port, baud_rate=self._baud_rate)
        await self._reader.start()
        self._running = True
        self._location.gps_state = "searching"
        asyncio.create_task(self._read_loop())
        logger.info("UBX location provider started", port=self._port)

    async def get_location(self) -> Location:
        return self._location

    async def _read_loop(self) -> None:
        while self._running and self._reader:
            try:
                pvt = await self._reader.read_pvt()
                if pvt and pvt.gnss_fix_ok and pvt.fix_type >= 2:
                    self._fix_count += 1
                    self._location = Location(
                        latitude=pvt.lat,
                        longitude=pvt.lon,
                        altitude=pvt.alt_msl_m,
                        horizontal_accuracy=pvt.hacc_m,
                        vertical_accuracy=pvt.vacc_m,
                        source="gps",
                        gps_state="fix",
                        fix_count=self._fix_count,
                        hdop=pvt.pdop,
                        sat_count=pvt.num_sv,
                        speed_ms=pvt.ground_speed_ms,
                        course_deg=pvt.heading_deg,
                    )
                    if self._fix_count <= 5 or self._fix_count % 60 == 0:
                        logger.info(
                            "UBX fix",
                            fix=self._fix_count,
                            lat=round(pvt.lat, 7),
                            lon=round(pvt.lon, 7),
                            sats=pvt.num_sv,
                            hacc=round(pvt.hacc_m, 2),
                        )
                elif pvt:
                    self._location.gps_state = "searching"
                    self._location.sat_count = pvt.num_sv
            except Exception as e:
                logger.warning("UBX read error", error=str(e))
            await asyncio.sleep(self._poll_interval)

    async def stop(self) -> None:
        self._running = False
        if self._reader:
            await self._reader.stop()
            self._reader = None
        logger.info("UBX location provider stopped", fixes=self._fix_count)


class GPSDLocationProvider(LocationProvider):
    """Location from the gpsd daemon (requires gpsd-py3)."""

    def __init__(self) -> None:
        self._location = Location(source="gpsd", gps_state="off")
        self._running = False

    async def get_location(self) -> Location:
        return self._location

    async def start(self) -> None:
        try:
            import gpsd
            gpsd.connect()
            self._running = True
            logger.info("GPSD location provider started")
            asyncio.create_task(self._update_loop())
        except ImportError:
            logger.warning("gpsd-py3 not installed; pip install gpsd-py3")
            raise
        except Exception as e:
            logger.error("Failed to connect to gpsd", error=str(e))
            raise

    async def _update_loop(self) -> None:
        import gpsd

        while self._running:
            try:
                packet = gpsd.get_current()
                if packet.mode >= 2:
                    self._location = Location(
                        latitude=packet.lat,
                        longitude=packet.lon,
                        altitude=packet.alt if packet.mode >= 3 else None,
                        horizontal_accuracy=packet.error.get("x"),
                        source="gpsd",
                        gps_state="fix",
                    )
                else:
                    self._location.gps_state = "searching"
            except Exception as e:
                logger.warning("GPSD error", error=str(e))
            await asyncio.sleep(1.0)

    async def stop(self) -> None:
        self._running = False
        logger.info("GPSD stopped")


async def create_location_provider(
    gps_enabled: bool = False,
    fixed_lat: float | None = None,
    fixed_lon: float | None = None,
    gps_port: str | None = None,
    gps_baud_rate: int = 9600,
    gps_module: str = "nmea",
) -> LocationProvider:
    """Create the appropriate location provider.

    Priority when gps_enabled:
    1. UBX (gps_module="zed_f9p" and serial port exists)
    2. Serial NMEA (gps_module="nmea" and serial port exists)
    3. gpsd
    4. Fixed fallback
    """
    if gps_enabled and platform.system() == "Linux":
        if gps_module == "zed_f9p" and gps_port and os.path.exists(gps_port):
            try:
                provider = UBXLocationProvider(
                    port=gps_port,
                    baud_rate=gps_baud_rate,
                    fallback_lat=fixed_lat,
                    fallback_lon=fixed_lon,
                )
                await provider.start()
                return provider
            except Exception as e:
                logger.warning("UBX GPS unavailable, trying NMEA", error=str(e))

        if gps_port and os.path.exists(gps_port):
            try:
                provider = SerialGPSLocationProvider(
                    port=gps_port,
                    baud_rate=gps_baud_rate,
                    fallback_lat=fixed_lat,
                    fallback_lon=fixed_lon,
                )
                await provider.start()
                return provider
            except Exception as e:
                logger.warning("Serial GPS unavailable, trying gpsd", error=str(e))

        try:
            provider = GPSDLocationProvider()
            await provider.start()
            return provider
        except Exception:
            logger.warning("gpsd unavailable, using fixed location")

    provider = FixedLocationProvider(fixed_lat, fixed_lon)
    await provider.start()
    return provider
