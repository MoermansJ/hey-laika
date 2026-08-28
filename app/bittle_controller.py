"""Hardware abstraction layer for the Petoi Bittle.

Three implementations behind one interface:
- MockBittleController   — no hardware, logs commands (Phase 0)
- SerialBittleController — USB serial (Phase 1)
- WiFiBittleController   — ESP8266 WiFi module (Phase 4)
"""
import logging
import time
from abc import ABC, abstractmethod

from app.config import Config

logger = logging.getLogger(__name__)


class BaseBittleController(ABC):
    mode = "base"

    @abstractmethod
    def connect(self) -> bool: ...

    @abstractmethod
    def disconnect(self) -> None: ...

    @abstractmethod
    def send_command(self, command: str) -> bool: ...

    @abstractmethod
    def get_status(self) -> dict: ...

    def get_telemetry(self) -> dict:
        """Battery/signal readout; None where the transport can't measure it."""
        return {"battery": None, "signal": None}


class MockBittleController(BaseBittleController):
    mode = "mock"

    # Simulated battery drain rate; wraps back to full as if swapped/recharged.
    BATTERY_DRAIN_PER_MINUTE = 1.5

    def __init__(self):
        self.connected = False
        self.last_command: str | None = None
        self.command_log: list[dict] = []
        self._battery_since = time.time()

    def connect(self) -> bool:
        self.connected = True
        logger.info("[mock] Bittle connected")
        return True

    def disconnect(self) -> None:
        self.connected = False

    def send_command(self, command: str) -> bool:
        if not self.connected:
            self.connect()
        self.last_command = command
        self.command_log.append({"command": command, "at": time.time()})
        # Keep the in-memory log bounded.
        self.command_log = self.command_log[-200:]
        logger.info("[mock] -> %s", command)
        return True

    def get_status(self) -> dict:
        return {
            "connected": self.connected,
            "mode": self.mode,
            "last_command": self.last_command,
            "commands_sent": len(self.command_log),
        }

    def get_telemetry(self) -> dict:
        minutes = (time.time() - self._battery_since) / 60
        battery = 100.0 - (minutes * self.BATTERY_DRAIN_PER_MINUTE) % 100.0
        return {"battery": round(battery, 1), "signal": "strong"}


class SerialBittleController(BaseBittleController):
    mode = "serial"

    def __init__(self, port: str, baudrate: int = 115200):
        self.port = port
        self.baudrate = baudrate
        self._serial = None

    def connect(self) -> bool:
        import serial  # lazy import so mock mode needs no hardware deps

        try:
            self._serial = serial.Serial(self.port, self.baudrate, timeout=2)
            time.sleep(2)  # Bittle's board resets on serial open
            return True
        except serial.SerialException as exc:
            logger.error("Serial connect failed on %s: %s", self.port, exc)
            self._serial = None
            return False

    def disconnect(self) -> None:
        if self._serial:
            self._serial.close()
            self._serial = None

    def send_command(self, command: str) -> bool:
        if self._serial is None and not self.connect():
            return False
        try:
            self._serial.write((command + "\n").encode("ascii"))
            return True
        except Exception as exc:
            logger.error("Serial write failed: %s", exc)
            return False

    def get_status(self) -> dict:
        return {"connected": self._serial is not None, "mode": self.mode, "port": self.port}


class WiFiBittleController(BaseBittleController):
    mode = "wifi"

    def __init__(self, host: str):
        self.host = host
        self.reachable = False

    def connect(self) -> bool:
        import requests

        try:
            requests.get(f"http://{self.host}/", timeout=3)
            self.reachable = True
        except requests.RequestException as exc:
            logger.error("WiFi module unreachable at %s: %s", self.host, exc)
            self.reachable = False
        return self.reachable

    def disconnect(self) -> None:
        self.reachable = False

    def send_command(self, command: str) -> bool:
        import requests

        try:
            resp = requests.get(f"http://{self.host}/cmd", params={"c": command}, timeout=3)
            return resp.ok
        except requests.RequestException as exc:
            logger.error("WiFi command failed: %s", exc)
            return False

    def get_status(self) -> dict:
        return {"connected": self.reachable, "mode": self.mode, "host": self.host}


def create_bittle_controller(config: type[Config] = Config) -> BaseBittleController:
    method = "mock" if config.MOCK_MODE else config.BITTLE_COMMUNICATION_METHOD
    if method == "serial":
        return SerialBittleController(config.BITTLE_SERIAL_PORT)
    if method == "wifi":
        return WiFiBittleController(config.BITTLE_WIFI_HOST)
    return MockBittleController()
