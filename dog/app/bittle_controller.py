"""Hardware abstraction layer for the Petoi Bittle.

Three implementations behind one interface:
- MockBittleController   — no hardware, logs commands and tracks virtual joints
- SerialBittleController — USB serial (validated against firmware B10_251121)
- WiFiBittleController   — WebSocket client for the stock BiBoard firmware
                           (ws://<host>:81, JSON task frames, b64: binary)

Serial protocol facts validated live 2026-08-30 (docs/robot/VALIDATION_RESULTS.md
in the orchestrator repo):
- 115200 8N1, lines end \r\n; opening the port does NOT reboot the board
- lowercase tokens are ASCII lines; uppercase are binary int8 args + '~'
- the firmware echoes the command token on COMPLETION (moves are interpolated
  at ~4 ms/degree); skills echo a bare 'k' after a skill-name line
- commands sent while the firmware is busy are silently DROPPED, so every
  exchange must be a locked write→await-echo transaction
- unsolicited lines (voice module 'X…') can appear mid-stream and must be
  tolerated; 'p' echoes uppercase 'P'
"""
import logging
import re
import struct
import threading
import time
from abc import ABC, abstractmethod

from app.config import Config

logger = logging.getLogger(__name__)

JOINT_COUNT = 16
# Bittle X has 9 physical servos; indices 1-7 are placeholders in every frame.
PHYSICAL_JOINTS = (0, 8, 9, 10, 11, 12, 13, 14, 15)
INT8_MIN, INT8_MAX = -125, 125

# Firmware serial buffer limit: chunk writes to 20 bytes with a small gap.
_WRITE_CHUNK = 20
_WRITE_GAP_S = 0.001

# Echo timeouts by command family. Move echoes signal completion and scale
# with distance (~4 ms/deg), so 3s covers any single move with margin.
_TIMEOUT_SKILL = 8.0
_TIMEOUT_DEFAULT = 3.0
# The WS task queue adds latency and the firmware's own task timeout is 45s;
# observed: first skill after boot can exceed 8s before 'completed' arrives.
_TIMEOUT_SKILL_WS = 20.0

# Battery: firmware 'P' (T_POWER) prints "Voltage: x.xx V" from the pack
# divider. 2S LiPo: ~8.35 V full, ~6.8 V at the firmware's low-power floor.
# Linear map is approximate (LiPo curves sag under load) but good enough
# for a gauge. Cached so status polling doesn't occupy the robot.
_VOLTAGE_RE = re.compile(r"Voltage:\s*([0-9]+(?:\.[0-9]+)?)")
_BATT_FULL_V = 8.35
_BATT_EMPTY_V = 6.8
_TELEMETRY_TTL_S = 20.0


def _voltage_to_percent(voltage: float) -> float:
    pct = (voltage - _BATT_EMPTY_V) / (_BATT_FULL_V - _BATT_EMPTY_V) * 100.0
    return round(max(0.0, min(100.0, pct)), 1)


def _parse_voltage(lines: list[str]) -> float | None:
    match = _VOLTAGE_RE.search("\n".join(lines))
    return float(match.group(1)) if match else None


def _echo_token(command: str) -> str:
    """The token the firmware echoes for an ASCII command line."""
    if not command:
        return ""
    # Skills ('kbalance') echo a bare 'k' after a skill-name line.
    return command[0]


class BaseBittleController(ABC):
    mode = "base"
    # Wall-clock of the last motion/skill command; the host-side idle keeper
    # reads this to settle the robot when nothing has moved it for a while.
    last_motion_at: float | None = None

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

    def query(self, command: str) -> list[str] | None:
        """Send a command and return the firmware's output lines.

        Unlike send_command (success bool only), this surfaces the payload —
        needed for sensor reads like 'gp' (IMU) or 'P' (voltage). None means
        the exchange failed or the transport can't capture output.
        """
        return None

    def get_info(self) -> dict:
        """Model/firmware identity where the transport can query it."""
        return {"model": None, "firmwareVersion": None}

    def move_joints(self, moves: list[tuple[int, int]]) -> bool:
        """Move joints simultaneously; not supported on this transport."""
        return False

    def read_joint_angles(self) -> list[int] | None:
        """Current firmware-target angles (16 values); None if unsupported.

        Note: these are COMMANDED angles — the servos have no position
        feedback, so a stalled joint still reads its target.
        """
        return None


class MockBittleController(BaseBittleController):
    mode = "mock"

    # Simulated battery drain rate; wraps back to full as if swapped/recharged.
    BATTERY_DRAIN_PER_MINUTE = 1.5

    def __init__(self):
        self.connected = False
        self.last_command: str | None = None
        self.command_log: list[dict] = []
        self._battery_since = time.time()
        self._joint_angles = [0] * JOINT_COUNT

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
        self.last_motion_at = time.time()
        self.command_log.append({"command": command, "at": time.time()})
        # Keep the in-memory log bounded.
        self.command_log = self.command_log[-200:]
        logger.info("[mock] -> %s", command)
        return True

    def move_joints(self, moves: list[tuple[int, int]]) -> bool:
        for index, angle in moves:
            self._joint_angles[index] = angle
        return self.send_command(
            "I " + " ".join(f"{i}:{a}" for i, a in moves))

    def read_joint_angles(self) -> list[int] | None:
        return list(self._joint_angles)

    def get_info(self) -> dict:
        return {"model": "Bittle X (mock)", "firmwareVersion": "mock"}

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
        self._lock = threading.RLock()
        self.last_command: str | None = None
        self.commands_sent = 0
        self._info: dict = {"model": None, "firmwareVersion": None}
        self._telemetry: dict = {"battery": None, "signal": None}
        self._telemetry_at = 0.0

    def connect(self) -> bool:
        import serial  # lazy import so mock mode needs no hardware deps

        try:
            with self._lock:
                self._serial = serial.Serial(self.port, self.baudrate,
                                             timeout=0.05)
                # Validated: no DTR reboot on open; a short settle + buffer
                # drain clears any in-flight noise from a previous session.
                time.sleep(0.5)
                self._serial.reset_input_buffer()
                found, payload = self._transact(b"?\n", "?", _TIMEOUT_DEFAULT)
                if found and len(payload) >= 2:
                    self._info = {"model": payload[0],
                                  "firmwareVersion": payload[1]}
                logger.info("Serial connected on %s: %s", self.port, self._info)
                return True
        except serial.SerialException as exc:
            logger.error("Serial connect failed on %s: %s", self.port, exc)
            self._serial = None
            return False

    def disconnect(self) -> None:
        with self._lock:
            if self._serial:
                self._serial.close()
                self._serial = None

    # ---- transaction core -------------------------------------------------

    def _write_chunked(self, payload: bytes) -> None:
        for i in range(0, len(payload), _WRITE_CHUNK):
            self._serial.write(payload[i:i + _WRITE_CHUNK])
            if i + _WRITE_CHUNK < len(payload):
                time.sleep(_WRITE_GAP_S)

    def _transact(self, payload: bytes, echo: str,
                  timeout: float) -> tuple[bool, list[str]]:
        """Write one command and read until its echo line arrives.

        Holds the port lock for the whole exchange: the firmware drops any
        command received while busy, so concurrent callers must queue here.
        Returns (echo_seen, payload_lines_before_echo).
        """
        with self._lock:
            if self._serial is None:
                raise RuntimeError("serial port not open")
            self._serial.reset_input_buffer()
            self._write_chunked(payload)
            buf = b""
            deadline = time.time() + timeout
            while time.time() < deadline:
                waiting = self._serial.in_waiting
                chunk = self._serial.read(waiting or 1)
                if not chunk:
                    continue
                buf += chunk
                text = buf.decode(errors="ignore")
                text = text.replace("\r\n", "\n").replace("\r", "\n")
                lines = text.split("\n")
                # Only lines terminated by a newline are complete.
                complete, partial = lines[:-1], lines[-1]
                for pos, line in enumerate(complete):
                    # Case-insensitive: 'p' echoes 'P'; skills echo bare 'k'.
                    if line.strip().lower() == echo.lower():
                        payload_lines = [l for l in complete[:pos] if l.strip()]
                        return True, payload_lines
            leftovers = buf.decode(errors="ignore")
            logger.warning("No '%s' echo within %.1fs; got %r",
                           echo, timeout, leftovers[:200])
            return False, [l for l in leftovers.splitlines() if l.strip()]

    # ---- public API -------------------------------------------------------

    def send_command(self, command: str) -> bool:
        if self._serial is None and not self.connect():
            return False
        timeout = _TIMEOUT_SKILL if command.startswith(("k", "K", "X")) \
            else _TIMEOUT_DEFAULT
        try:
            found, _ = self._transact((command + "\n").encode("ascii"),
                                      _echo_token(command), timeout)
        except Exception as exc:
            logger.error("Serial command failed: %s", exc)
            return False
        self.last_command = command
        self.last_motion_at = time.time()
        self.commands_sent += 1
        return found

    def move_joints(self, moves: list[tuple[int, int]]) -> bool:
        """Simultaneous joint move via the binary 'I' command.

        The echo arrives on motion COMPLETION (firmware interpolates), so a
        True return means the joints have reached their targets.
        """
        if not moves:
            return True
        for index, angle in moves:
            if index not in PHYSICAL_JOINTS:
                raise ValueError(f"invalid joint index {index}")
            if not INT8_MIN <= angle <= INT8_MAX:
                raise ValueError(f"angle {angle} outside {INT8_MIN}..{INT8_MAX}")
        if self._serial is None and not self.connect():
            return False
        payload = b"I" + b"".join(
            struct.pack("bb", i, a) for i, a in moves) + b"~"
        try:
            found, _ = self._transact(payload, "I", _TIMEOUT_DEFAULT)
        except Exception as exc:
            logger.error("Serial move failed: %s", exc)
            return False
        self.last_command = "I " + " ".join(f"{i}:{a}" for i, a in moves)
        self.commands_sent += 1
        return found

    def read_joint_angles(self) -> list[int] | None:
        if self._serial is None and not self.connect():
            return None
        try:
            found, payload = self._transact(b"j\n", "j", _TIMEOUT_DEFAULT)
        except Exception as exc:
            logger.error("Serial joint read failed: %s", exc)
            return None
        if not found:
            return None
        # Response: '=', a tab-separated index header, then the comma-separated
        # angle row; unsolicited 'X…' voice-module lines may interleave.
        for line in payload:
            if "," not in line:
                continue
            try:
                values = [int(tok.strip().rstrip(","))
                          for tok in line.split() if tok.strip().rstrip(",")]
            except ValueError:
                continue
            if len(values) == JOINT_COUNT:
                return values
        logger.warning("j readback had no %d-value angle line: %r",
                       JOINT_COUNT, payload)
        return None

    def query(self, command: str) -> list[str] | None:
        if self._serial is None and not self.connect():
            return None
        timeout = _TIMEOUT_SKILL if command.startswith(("k", "K", "X")) \
            else _TIMEOUT_DEFAULT
        try:
            found, payload = self._transact((command + "\n").encode("ascii"),
                                            _echo_token(command), timeout)
        except Exception as exc:
            logger.error("Serial query failed: %s", exc)
            return None
        return payload if found else None

    def get_telemetry(self) -> dict:
        if time.time() - self._telemetry_at < _TELEMETRY_TTL_S:
            return dict(self._telemetry)
        telemetry = {"battery": None, "signal": None}
        if self._serial is not None or self.connect():
            try:
                found, payload = self._transact(b"P~", "P", _TIMEOUT_DEFAULT)
            except Exception as exc:
                logger.error("Serial voltage read failed: %s", exc)
                found, payload = False, []
            voltage = _parse_voltage(payload) if found else None
            if voltage is not None:
                telemetry["battery"] = _voltage_to_percent(voltage)
        self._telemetry, self._telemetry_at = telemetry, time.time()
        return dict(telemetry)

    def get_info(self) -> dict:
        return dict(self._info)

    def get_status(self) -> dict:
        return {
            "connected": self._serial is not None,
            "mode": self.mode,
            "port": self.port,
            "last_command": self.last_command,
            "commands_sent": self.commands_sent,
        }


class WiFiBittleController(BaseBittleController):
    """WebSocket client for the stock BiBoard firmware (ws://<host>:81).

    Protocol per opencat-esp32 webServer.h and the official app
    (petoi/pyUI/SkillComposer.py): send {"type":"command","taskId":…,
    "commands":[…]}; replies carry the same taskId with status
    running/completed/error and a results list. Binary commands go as
    "b64:" + base64(token byte + int8 args) — the firmware re-appends the
    '~' terminator itself. The firmware caps connections at 2 clients and
    drops any client idle >40s, so we hold ONE connection and reconnect on
    demand; any frame refreshes the idle timer. 'completed' arrives when
    the motion finishes, matching the serial controller's echo semantics.
    """
    mode = "wifi"

    def __init__(self, host: str, port: int = 81):
        self.host = host
        self.port = port
        self._ws = None
        self._lock = threading.RLock()
        self._task_seq = 0
        self.last_command: str | None = None
        self.commands_sent = 0
        self._info: dict = {"model": None, "firmwareVersion": None}
        self._telemetry: dict = {"battery": None, "signal": None}
        self._telemetry_at = 0.0
        # Called (in a worker thread) whenever the robot transitions from
        # unreachable to connected — the host-side "robot came online" event
        # that boot/greeting behavior hangs off now that firmware is silent.
        self.on_online = None
        self._was_connected = False
        # Called (in a worker thread) for interesting unsolicited firmware
        # output that rides along in task results (e.g. EXCEPTION_REPORT
        # lines from the reflex-free custom firmware).
        self.on_output_line = None

    def connect(self) -> bool:
        import websocket  # lazy import so mock mode needs no hardware deps

        with self._lock:
            self.disconnect()
            try:
                self._ws = websocket.create_connection(
                    f"ws://{self.host}:{self.port}", timeout=3)
            except Exception as exc:
                logger.error("WiFi WS connect failed to %s:%s: %s",
                             self.host, self.port, exc)
                self._ws = None
                # Robot genuinely unreachable: the next successful connect is
                # a came-online transition (idle socket cycling is not).
                self._was_connected = False
                return False
            # '?' returns the boot banner; the model name and version are
            # the first two non-empty lines, same as over serial.
            lines = self._transact("?", timeout=18.0)
            if lines:
                text = [l.strip() for l in "\n".join(lines).splitlines()
                        if l.strip()]
                # Stale frames from a dropped task can pollute the banner;
                # only trust it when the first line looks like a model name.
                if len(text) >= 2 and len(text[0]) > 2:
                    self._info = {"model": text[0],
                                  "firmwareVersion": text[1].split()[-1]}
            logger.info("WiFi WS connected to %s:%s: %s",
                        self.host, self.port, self._info)
            came_online = not self._was_connected
            self._was_connected = True
        if came_online and self.on_online is not None:
            threading.Thread(target=self.on_online, daemon=True).start()
        return True

    def disconnect(self) -> None:
        with self._lock:
            if self._ws is not None:
                try:
                    self._ws.close()
                except Exception:
                    pass
                self._ws = None

    # ---- transaction core -------------------------------------------------

    def _next_task_id(self) -> str:
        self._task_seq += 1
        return f"{int(time.time() * 1000)}-{self._task_seq}"

    def _surface_output(self, lines: list[str]) -> None:
        """Dispatch interesting unsolicited lines to the host, off-thread
        (we hold the controller lock here; listeners may need other locks)."""
        if self.on_output_line is None:
            return
        for raw in "\n".join(lines).splitlines():
            line = raw.strip()
            if line.startswith("EXCEPTION_REPORT"):
                threading.Thread(target=self.on_output_line, args=(line,),
                                 daemon=True).start()

    def _transact(self, command: str, timeout: float) -> list[str] | None:
        """Send one command frame and wait for its completed/error reply.

        Holds the lock for the whole exchange (single connection, and the
        firmware runs one web task at a time). Returns the results lines on
        completion, [] on completion without payload, None on error/timeout.
        """
        import json

        with self._lock:
            if self._ws is None:
                raise RuntimeError("websocket not connected")
            task_id = self._next_task_id()
            self._ws.send(json.dumps({
                "type": "command",
                "taskId": task_id,
                "commands": [command],
                "timestamp": int(time.time() * 1000),
            }))
            deadline = time.time() + timeout
            self._ws.settimeout(min(timeout, 5.0))
            while time.time() < deadline:
                try:
                    raw = self._ws.recv()
                except Exception:
                    continue  # recv timeout tick; keep waiting until deadline
                if isinstance(raw, bytes):
                    raw = raw.decode("utf-8", errors="replace")
                try:
                    frame = json.loads(raw)
                except (json.JSONDecodeError, TypeError):
                    continue
                if frame.get("type") in ("connected", "heartbeat"):
                    continue
                if str(frame.get("taskId")) != task_id:
                    continue
                status = (frame.get("status") or "").lower()
                if status == "running":
                    continue
                if status == "completed":
                    results = frame.get("results")
                    if isinstance(results, list):
                        lines = [str(r) for r in results]
                    elif isinstance(results, str):
                        lines = [results]
                    else:
                        lines = []
                    self._surface_output(lines)
                    return lines
                if status == "error":
                    logger.warning("WiFi command errored: %r -> %r",
                                   command, frame.get("error"))
                    return None
            logger.warning("No completion for %r within %.1fs", command,
                           timeout)
            return None

    def _heartbeat_ok(self) -> bool:
        """Probe the socket: True if the firmware echoes a heartbeat frame."""
        import json

        try:
            self._ws.send(json.dumps({"type": "heartbeat"}))
            deadline = time.time() + min(2.5, _TIMEOUT_DEFAULT)
            self._ws.settimeout(1.0)
            while time.time() < deadline:
                try:
                    frame = json.loads(self._ws.recv())
                except Exception:
                    continue
                if frame.get("type") == "heartbeat":
                    return True
        except Exception:
            pass
        return False

    def _send(self, command: str, timeout: float) -> list[str] | None:
        """_transact with one reconnect-and-retry (firmware drops idle clients).

        Retries happen only when the socket is provably dead (send raised, or
        a completion timeout AND a failed heartbeat probe) — if the firmware
        answers the probe, the command reached it and must NOT be re-sent,
        or motion could execute twice.
        """
        with self._lock:
            if self._ws is None and not self.connect():
                return None
            try:
                result = self._transact(command, timeout)
                if result is not None:
                    return result
                if self._heartbeat_ok():
                    return None  # firmware alive; command lost/slow — no retry
                logger.warning("WiFi socket stale after timeout; reconnecting "
                               "and retrying %r", command)
            except Exception as exc:
                logger.warning("WiFi send failed (%s); reconnecting", exc)
            if not self.connect():
                return None
            try:
                return self._transact(command, timeout)
            except Exception as exc2:
                logger.error("WiFi command failed after retry: %s", exc2)
                self.disconnect()
                return None

    # ---- public API -------------------------------------------------------

    def send_command(self, command: str) -> bool:
        timeout = _TIMEOUT_SKILL_WS if command.startswith(("k", "K", "X")) \
            else _TIMEOUT_DEFAULT
        result = self._send(command, timeout)
        if result is None:
            return False
        self.last_command = command
        self.last_motion_at = time.time()
        self.commands_sent += 1
        return True

    def move_joints(self, moves: list[tuple[int, int]]) -> bool:
        import base64

        if not moves:
            return True
        for index, angle in moves:
            if index not in PHYSICAL_JOINTS:
                raise ValueError(f"invalid joint index {index}")
            if not INT8_MIN <= angle <= INT8_MAX:
                raise ValueError(f"angle {angle} outside {INT8_MIN}..{INT8_MAX}")
        payload = b"I" + b"".join(struct.pack("bb", i, a) for i, a in moves)
        command = "b64:" + base64.b64encode(payload).decode("ascii")
        if self._send(command, _TIMEOUT_DEFAULT) is None:
            return False
        self.last_command = "I " + " ".join(f"{i}:{a}" for i, a in moves)
        self.commands_sent += 1
        return True

    def read_joint_angles(self) -> list[int] | None:
        results = self._send("j", _TIMEOUT_DEFAULT)
        if results is None:
            return None
        for line in "\n".join(results).splitlines():
            if "," not in line:
                continue
            try:
                values = [int(tok.strip().rstrip(","))
                          for tok in line.split() if tok.strip().rstrip(",")]
            except ValueError:
                continue
            if len(values) == JOINT_COUNT:
                return values
        logger.warning("j readback had no %d-value angle line: %r",
                       JOINT_COUNT, results)
        return None

    def query(self, command: str) -> list[str] | None:
        timeout = _TIMEOUT_SKILL_WS if command.startswith(("k", "K", "X")) \
            else _TIMEOUT_DEFAULT
        return self._send(command, timeout)

    def get_telemetry(self) -> dict:
        if time.time() - self._telemetry_at < _TELEMETRY_TTL_S:
            return dict(self._telemetry)
        telemetry = {"battery": None, "signal": None}
        results = self._send("P", _TIMEOUT_DEFAULT)
        voltage = _parse_voltage(results) if results else None
        if voltage is not None:
            telemetry = {"battery": _voltage_to_percent(voltage),
                         "signal": "wifi"}
        self._telemetry, self._telemetry_at = telemetry, time.time()
        return dict(telemetry)

    def get_info(self) -> dict:
        return dict(self._info)

    def get_status(self) -> dict:
        return {
            "connected": self._ws is not None,
            "mode": self.mode,
            "host": self.host,
            "last_command": self.last_command,
            "commands_sent": self.commands_sent,
        }


def create_bittle_controller(config: type[Config] = Config) -> BaseBittleController:
    method = "mock" if config.MOCK_MODE else config.BITTLE_COMMUNICATION_METHOD
    if method == "serial":
        return SerialBittleController(config.BITTLE_SERIAL_PORT,
                                      config.BITTLE_SERIAL_BAUD)
    if method == "wifi":
        return WiFiBittleController(config.BITTLE_WIFI_HOST,
                                    config.BITTLE_WIFI_PORT)
    return MockBittleController()
