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
# After a dropped 'P' the cache holds {None, None} only this long, so a
# single lost poll cannot mask a low battery for the full telemetry TTL.
_TELEMETRY_RETRY_S = 5.0
# With the robot down, read-only polls skip the reconnect attempt for this
# long after a failed connect (each attempt costs a 3 s timeout).
_CONNECT_BACKOFF_S = 10.0

# Commands that may be re-sent after a reconnect: pure reads. Everything
# else (skills, joint moves, calibration, beeps, module toggles) could have
# reached the firmware before the link died and must never run twice.
_RETRY_SAFE = ("?", "P", "j", "gp", "X?", "XWs", "XWr")
# Commands that do not move the robot and therefore must not reset the idle
# ladder or block the WiFi sniffer: beeps, reads, and X-tool/module toggles.
_NON_MOTION_PREFIXES = ("b", "B", "X", "?", "P", "j", "J", "gp", "G", "v")


def _retry_safe(command: str) -> bool:
    return command in _RETRY_SAFE or command.startswith(("X?", "XWs", "XWr"))


def _is_motion(command: str) -> bool:
    return not command.startswith(_NON_MOTION_PREFIXES)


def _is_closed_error(exc: BaseException) -> bool:
    """True when a socket error means the link is gone (not a timeout)."""
    if isinstance(exc, (TimeoutError,)):
        return False
    name = type(exc).__name__
    if "Timeout" in name:
        return False
    return isinstance(exc, (OSError, ConnectionError, RuntimeError)) \
        or "Closed" in name or "closed" in str(exc).lower()


class _SendFailed(Exception):
    """The command never left the host (socket write failed)."""


class _LinkLost(Exception):
    """The socket died after the command was written; delivery unknown."""

# Battery: firmware 'P' (T_POWER) prints "Voltage: x.xx V" from the pack
# divider. 2S LiPo: ~8.35 V full, ~6.8 V at the firmware's low-power floor.
# Linear map is approximate (LiPo curves sag under load) but good enough
# for a gauge. Cached so status polling doesn't occupy the robot.
_VOLTAGE_RE = re.compile(r"Voltage:\s*([0-9]+(?:\.[0-9]+)?)")
_BATT_FULL_V = 8.35
_BATT_EMPTY_V = 6.8
_TELEMETRY_TTL_S = 40.0  # halved dog-facing 'P' polls (owner request)


def _voltage_to_percent(voltage: float) -> float:
    pct = (voltage - _BATT_EMPTY_V) / (_BATT_FULL_V - _BATT_EMPTY_V) * 100.0
    return round(max(0.0, min(100.0, pct)), 1)


def _parse_voltage(lines: list[str]) -> float | None:
    match = _VOLTAGE_RE.search("\n".join(lines))
    return float(match.group(1)) if match else None


_RANGE_RE = re.compile(r"=\s*\r?\n?\s*(-?\d+(?:\.\d+)?)")


def _parse_range(lines: list[str]) -> float | None:
    """'=' then the centimetre reading on the next line (or same line);
    the firmware prints -1 / 0 for no echo."""
    match = _RANGE_RE.search("\n".join(lines))
    if not match:
        return None
    value = float(match.group(1))
    return value if value > 0 else None


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
    # Telemetry cache TTL; the app may replace this with the adaptive poll
    # policy's callable (idle postures stretch it).
    telemetry_ttl = staticmethod(lambda: _TELEMETRY_TTL_S)

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

    def abort(self) -> bool:
        """Drop queued firmware work and rest immediately. Only the WiFi
        transport (hey-laika firmware) supports it; others return False."""
        return False

    def read_range_cm(self, pin: int) -> float | None:
        """One-shot ultrasonic read on a one-pin Grove ranger (firmware 'XU'
        with trigger == echo pin). None when unsupported or no echo."""
        return None

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
        # MOCK_RICH: synthesize the firmware's push/scan surfaces so the GUI
        # has live-looking data (leash RSSI walk, WiFi fingerprints).
        self.on_event_frame = None
        if Config.MOCK_RICH:
            threading.Thread(target=self._rich_loop, daemon=True).start()

    def _rich_loop(self) -> None:
        import random

        rssi = -55.0
        while True:
            time.sleep(1.0)
            rssi = max(-92.0, min(-42.0, rssi + random.uniform(-2.5, 2.5)))
            if self.on_event_frame is not None:
                frame = {"type": "event_rssi", "rssi": round(rssi),
                         "ssid": "MockSpot",
                         "timestamp": int(time.time() * 1000)}
                threading.Thread(target=self.on_event_frame, args=(frame,),
                                 daemon=True).start()

    def query(self, command: str) -> list[str] | None:
        if Config.MOCK_RICH and command.startswith("XWs"):
            import random

            aps = [("MockSpot", "AA:00:00:00:00:01", -50, 1),
                   ("neighbor-upstairs", "BB:00:00:00:00:02", -72, 6),
                   ("neighbor-left", "CC:00:00:00:00:03", -83, 11),
                   ("cafe-below", "DD:00:00:00:00:04", -90, 1)]
            lines = ["="] + [
                ('{"ssid":"%s","bssid":"%s","rssi":%d,"channel":%d}'
                 % (s, b, r + random.randint(-4, 4), ch))
                for s, b, r, ch in aps] + ["X"]
            return ["\r\n".join(lines)]
        return None

    def connect(self) -> bool:
        self.connected = True
        logger.info("[mock] Bittle connected")
        return True

    def disconnect(self) -> None:
        self.connected = False

    def abort(self) -> bool:
        logger.info("[mock] abort")
        return True

    def read_range_cm(self, pin: int) -> float | None:
        import random

        return round(random.uniform(18.0, 160.0), 1)

    def query_binary(self, payload: bytes) -> list[str] | None:
        self.send_command(payload[:3].decode("ascii", errors="replace")
                          + f"<{len(payload) - 3} bytes>")
        return ["=", "8192"]

    def send_command(self, command: str) -> bool:
        if not self.connected:
            self.connect()
        self.last_command = command
        if _is_motion(command):
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
        # Drains to a 20% floor and holds there: a fixture must never trip
        # the 5% battery.low safety binding (rest_now) on its own.
        minutes = (time.time() - self._battery_since) / 60
        battery = max(20.0, 100.0 - minutes * self.BATTERY_DRAIN_PER_MINUTE)
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
        if _is_motion(command):
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
        self.last_motion_at = time.time()
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
        if time.time() - self._telemetry_at < self.telemetry_ttl():
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
        # Called (in a worker thread) with every unsolicited event frame the
        # firmware pushes (event_rssi, event_us, ...). Fed both by the idle
        # pump below and by frames interleaved into command exchanges.
        self.on_event_frame = None
        # Idle pump: between transactions nobody would read the socket, so
        # pushed event frames would pile up and the firmware's 40s
        # client-silence timeout would drop us. The pump drains frames and
        # heartbeats the link whenever the transaction lock is free.
        self._pump_stop = threading.Event()
        self._last_keepalive = 0.0
        self._last_connect_failure = 0.0
        threading.Thread(target=self._pump_loop, daemon=True).start()

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
                self._last_connect_failure = time.time()
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

    def _dispatch_event(self, frame: dict) -> None:
        if self.on_event_frame is None:
            return
        threading.Thread(target=self.on_event_frame, args=(frame,),
                         daemon=True).start()

    def _pump_loop(self) -> None:
        import json

        while not self._pump_stop.wait(0.5):
            if not self._lock.acquire(blocking=False):
                continue  # a transaction is running; it dispatches events
            try:
                if self._ws is None:
                    continue
                now = time.time()
                if now - self._last_keepalive > 20.0:
                    # Refresh the firmware's client-silence timer so the
                    # connection (and its 1 Hz event_rssi stream) stays up.
                    try:
                        self._ws.send(json.dumps({"type": "heartbeat"}))
                        self._last_keepalive = now
                    except Exception:
                        # Socket is dead (robot powered off / WiFi gone):
                        # clear it so get_status reports connected=False
                        # honestly — the power tracker keys off this.
                        self.disconnect()
                        continue
                self._ws.settimeout(0.05)
                while True:
                    try:
                        raw = self._ws.recv()
                    except Exception as exc:
                        if _is_closed_error(exc):
                            # Peer went away: drop the socket now so
                            # get_status()['connected'] and the power
                            # tracker stop lying until the next keepalive.
                            logger.warning("WiFi socket closed by peer (%s)",
                                           exc)
                            self.disconnect()
                        break
                    if isinstance(raw, bytes):
                        raw = raw.decode("utf-8", errors="replace")
                    try:
                        frame = json.loads(raw)
                    except (json.JSONDecodeError, TypeError):
                        continue
                    if str(frame.get("type", "")).startswith("event_"):
                        self._dispatch_event(frame)
            except Exception:
                logger.exception("WiFi event pump tick failed")
            finally:
                self._lock.release()

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
            try:
                self._ws.send(json.dumps({
                    "type": "command",
                    "taskId": task_id,
                    "commands": [command],
                    "timestamp": int(time.time() * 1000),
                }))
            except Exception as exc:
                raise _SendFailed(str(exc)) from exc
            deadline = time.time() + timeout
            self._ws.settimeout(min(timeout, 5.0))
            while time.time() < deadline:
                try:
                    raw = self._ws.recv()
                except Exception as exc:
                    if _is_closed_error(exc):
                        # A closed socket raises instantly; spinning on it
                        # for the whole timeout would hold the lock for up
                        # to 20 s at 100% CPU. Delivery is unknown.
                        raise _LinkLost(str(exc)) from exc
                    continue  # recv timeout tick; keep waiting until deadline
                if isinstance(raw, bytes):
                    raw = raw.decode("utf-8", errors="replace")
                try:
                    frame = json.loads(raw)
                except (json.JSONDecodeError, TypeError):
                    continue
                if frame.get("type") in ("connected", "heartbeat"):
                    continue
                if str(frame.get("type", "")).startswith("event_"):
                    self._dispatch_event(frame)  # don't lose pushes mid-command
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
                except Exception as exc:
                    if _is_closed_error(exc):
                        return False
                    continue
                if frame.get("type") == "heartbeat":
                    return True
        except Exception:
            pass
        return False

    def abort(self) -> bool:
        """Ask the firmware to drop its task queue and rest now (hey-laika
        abort frame). Best-effort: True only when the firmware acknowledges."""
        import json

        with self._lock:
            if self._ws is None and not self.connect():
                return False
            try:
                self._ws.send(json.dumps({"type": "abort"}))
                deadline = time.time() + 2.0
                self._ws.settimeout(1.0)
                while time.time() < deadline:
                    try:
                        frame = json.loads(self._ws.recv())
                    except Exception as exc:
                        if _is_closed_error(exc):
                            return False
                        continue
                    if str(frame.get("type", "")).startswith("event_"):
                        self._dispatch_event(frame)
                        continue
                    if frame.get("type") == "abort":
                        return str(frame.get("status", "")).lower() == "ok"
            except Exception as exc:
                logger.warning("WiFi abort failed: %s", exc)
            return False

    def _send(self, command: str, timeout: float) -> list[str] | None:
        """_transact with one reconnect-and-retry (firmware drops idle clients).

        Retries happen only when the socket is provably dead (send raised, or
        a completion timeout AND a failed heartbeat probe) — if the firmware
        answers the probe, the command reached it and must NOT be re-sent,
        or motion could execute twice.
        """
        with self._lock:
            if self._ws is None:
                # While the robot is down, every status poll would otherwise
                # spend a 3 s connect timeout under the lock and push the
                # adapter past the orchestrator's polling deadline. Reads
                # back off; commands always try.
                since_failure = time.time() - self._last_connect_failure
                if _retry_safe(command) and since_failure < _CONNECT_BACKOFF_S:
                    return None
                if not self.connect():
                    return None
            delivered = True  # unless the write itself failed
            try:
                result = self._transact(command, timeout)
                if result is not None:
                    return result
                if self._heartbeat_ok():
                    return None  # firmware alive; command lost/slow — no retry
                logger.warning("WiFi socket stale after timeout on %r; "
                               "reconnecting", command)
            except _SendFailed as exc:
                delivered = False
                logger.warning("WiFi send failed (%s); reconnecting", exc)
            except _LinkLost as exc:
                logger.warning("WiFi link lost during %r (%s); reconnecting",
                               command, exc)
            except Exception as exc:
                logger.warning("WiFi command error (%s); reconnecting", exc)
            from app.metrics import metrics
            metrics.inc("ws.reconnects")
            if not self.connect():
                return None
            # Re-send only when the command provably never reached the
            # firmware, or is a pure read. A skill that may already be
            # executing must never be queued a second time.
            if delivered and not _retry_safe(command):
                logger.warning("Not re-sending %r after reconnect: delivery "
                               "unknown and the command is not idempotent",
                               command)
                metrics.inc("ws.retry_suppressed")
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
        if _is_motion(command):
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
        self.last_motion_at = time.time()
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

    def query_binary(self, payload: bytes) -> list[str] | None:
        """Send token + raw argument bytes through the firmware's b64 path
        (binary-safe: the firmware copies cmdLen bytes, no strlen)."""
        import base64

        if len(payload) > 2400:
            raise ValueError("binary command exceeds the firmware buffer")
        return self._send("b64:" + base64.b64encode(payload).decode("ascii"),
                          _TIMEOUT_DEFAULT)

    def read_range_cm(self, pin: int) -> float | None:
        """Firmware reaction.h: 'X' token, newCmd "U<trigger><echo>" with the
        pins as raw int8 bytes (cmdLen 3), replies '=' then the distance."""
        results = self.query_binary(b"XU" + struct.pack("bb", int(pin), int(pin)))
        if not results:
            return None
        return _parse_range(results)

    def get_telemetry(self) -> dict:
        if time.time() - self._telemetry_at < self.telemetry_ttl():
            return dict(self._telemetry)
        telemetry = {"battery": None, "signal": None}
        results = self._send("P", _TIMEOUT_DEFAULT)
        voltage = _parse_voltage(results) if results else None
        if voltage is not None:
            telemetry = {"battery": _voltage_to_percent(voltage),
                         "signal": "wifi"}
            self._telemetry_at = time.time()
        else:
            # Negative result: retry soon instead of caching the miss for
            # the full TTL (a lost 'P' must not hide a low battery).
            self._telemetry_at = (time.time() - self.telemetry_ttl()
                                  + _TELEMETRY_RETRY_S)
        self._telemetry = telemetry
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
