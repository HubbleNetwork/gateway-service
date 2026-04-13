"""Gateway API authentication: SDK key registration and token lifecycle."""

import json
import locale
import platform
import time
from pathlib import Path
from typing import Any

import httpx
import structlog

from hubble_gateway import __version__

logger = structlog.get_logger(__name__)

_TOKEN_EXPIRY_MARGIN_S = 60


def _device_id() -> str:
    machine_id_path = Path("/etc/machine-id")
    if machine_id_path.exists():
        return machine_id_path.read_text().strip()
    return platform.node()


def _device_model() -> str:
    model_path = Path("/proc/device-tree/model")
    if model_path.exists():
        return model_path.read_text().strip().rstrip("\x00")
    return platform.machine()


def _device_manufacturer() -> str:
    model = _device_model().lower()
    if "raspberry" in model:
        return "Raspberry Pi"
    return platform.system()


def _ble_adapter_state() -> str:
    hci_path = Path("/sys/class/bluetooth/hci0")
    return "on" if hci_path.exists() else "off"


def _build_registration_payload() -> dict[str, Any]:
    return {
        "sentAtMillis": int(time.time() * 1000),
        "deviceId": _device_id(),
        "type": "custom",
        "manufacturer": _device_manufacturer(),
        "model": _device_model(),
        "firmwareVersion": __version__,
        "locale": locale.getdefaultlocale()[0] or "en-US",
        "bleAdapterState": _ble_adapter_state(),
        "capabilities": ["ble_scan", "location"],
        "platform": {
            "os": platform.system(),
            "osVersion": platform.release(),
            "pythonVersion": platform.python_version(),
            "sdk": "hubble-gateway-python",
            "sdkVersion": __version__,
        },
    }


class GatewayAuth:
    """Manages gateway registration and Bearer-token lifecycle.

    Persists tokens to a local JSON file so the gateway survives
    restarts without re-registering.
    """

    def __init__(self, sdk_key: str, base_url: str, token_path: str = "~/.hubble-gateway/auth.json") -> None:
        self._sdk_key = sdk_key
        self._base_url = base_url.rstrip("/")
        self._token_path = Path(token_path).expanduser()

        self._gateway_id: str | None = None
        self._device_token: str | None = None
        self._refresh_token: str | None = None
        self._expires_at_ms: int = 0
        self.server_config: dict[str, Any] = {}
        self._client: httpx.AsyncClient | None = None
        self._load_persisted_tokens()

    @property
    def gateway_id(self) -> str | None:
        return self._gateway_id

    @property
    def is_registered(self) -> bool:
        return self._gateway_id is not None

    @property
    def has_valid_token(self) -> bool:
        if not self._device_token:
            return False
        return int(time.time() * 1000) < (self._expires_at_ms - _TOKEN_EXPIRY_MARGIN_S * 1000)

    async def start(self) -> None:
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(30.0),
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": f"hubble-gateway-python/{__version__}",
            },
        )

    async def stop(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    async def ensure_authenticated(self) -> bool:
        if self.has_valid_token:
            return True
        if self._refresh_token and self._gateway_id:
            if await self._refresh():
                return True
            logger.warning("Token refresh failed; will re-register")
            self._clear_tokens()
        return await self._register()

    async def authenticated_request(
        self, method: str, path: str, json_body: dict[str, Any] | None = None
    ) -> httpx.Response:
        if not await self.ensure_authenticated():
            raise RuntimeError("Gateway authentication failed")
        resp = await self._request(method, path, json_body, authenticated=True)
        if resp.status_code == 401:
            body = resp.json() if resp.content else {}
            if body.get("code") == "token_expired":
                logger.info("Token expired mid-request, refreshing")
                self._device_token = None
                if await self.ensure_authenticated():
                    resp = await self._request(method, path, json_body, authenticated=True)
        return resp

    async def _register(self) -> bool:
        payload = _build_registration_payload()
        logger.info("Registering gateway", base_url=self._base_url)
        resp = await self._request(
            "PUT", "/api/v1/gateways", json_body=payload,
            extra_headers={"X-Sdk-Key": self._sdk_key},
        )
        if resp.status_code not in (200, 201):
            logger.error("Registration failed", status=resp.status_code, body=resp.text[:300])
            return False
        data = resp.json()
        gid = data.get("gatewayId", "")
        dt = data.get("deviceToken", "")
        rt = data.get("refreshToken", "")
        exp = data.get("expiresInSeconds", 0)
        if not (gid and dt and rt and exp > 0):
            logger.error("Registration response missing required fields", data=data)
            return False
        self._gateway_id = gid
        self._device_token = dt
        self._refresh_token = rt
        self._expires_at_ms = int(time.time() * 1000) + exp * 1000
        self._apply_server_config(data)
        self._persist_tokens()
        logger.info("Gateway registered", gateway_id=gid, expires_in_s=exp)
        return True

    async def _refresh(self) -> bool:
        logger.info("Refreshing device token")
        resp = await self._request(
            "POST", "/api/v1/auth/refresh",
            json_body={"refreshToken": self._refresh_token},
        )
        if resp.status_code != 200:
            logger.warning("Token refresh failed", status=resp.status_code)
            return False
        data = resp.json()
        dt = data.get("deviceToken", "")
        rt = data.get("refreshToken", self._refresh_token)
        exp = data.get("expiresInSeconds", 0)
        if not (dt and exp > 0):
            return False
        self._device_token = dt
        self._refresh_token = rt
        self._expires_at_ms = int(time.time() * 1000) + exp * 1000
        self._persist_tokens()
        logger.info("Token refreshed", expires_in_s=exp)
        return True

    async def heartbeat(self) -> None:
        if not self._gateway_id:
            return
        payload = _build_registration_payload()
        resp = await self.authenticated_request(
            "PUT", f"/api/v1/gateways/{self._gateway_id}", json_body=payload,
        )
        if resp.status_code == 200:
            self._apply_server_config(resp.json())

    async def _request(
        self, method: str, path: str, json_body: dict[str, Any] | None = None,
        *, authenticated: bool = False, extra_headers: dict[str, str] | None = None,
    ) -> httpx.Response:
        assert self._client is not None, "call start() first"
        headers: dict[str, str] = {}
        if authenticated and self._device_token:
            headers["Authorization"] = f"Bearer {self._device_token}"
        if extra_headers:
            headers.update(extra_headers)
        return await self._client.request(
            method, f"{self._base_url}{path}", json=json_body, headers=headers,
        )

    def _apply_server_config(self, data: dict[str, Any]) -> None:
        config = data.get("config") or {}
        for key in ("uploadIntervalMs", "uploadBatchSize", "scanIntervalMs", "featureFlags"):
            if key in config:
                self.server_config[key] = config[key]

    def _persist_tokens(self) -> None:
        self._token_path.parent.mkdir(parents=True, exist_ok=True)
        self._token_path.write_text(json.dumps({
            "gatewayId": self._gateway_id,
            "deviceToken": self._device_token,
            "refreshToken": self._refresh_token,
            "expiresAtMs": self._expires_at_ms,
            "serverConfig": self.server_config,
        }))
        self._token_path.chmod(0o600)

    def _load_persisted_tokens(self) -> None:
        if not self._token_path.exists():
            return
        try:
            data = json.loads(self._token_path.read_text())
            self._gateway_id = data.get("gatewayId")
            self._device_token = data.get("deviceToken")
            self._refresh_token = data.get("refreshToken")
            self._expires_at_ms = data.get("expiresAtMs", 0)
            self.server_config = data.get("serverConfig", {})
            logger.info("Loaded persisted auth", gateway_id=self._gateway_id)
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Failed to load persisted auth", error=str(exc))

    def _clear_tokens(self) -> None:
        self._device_token = None
        self._refresh_token = None
        self._expires_at_ms = 0
        if self._token_path.exists():
            self._token_path.unlink(missing_ok=True)
