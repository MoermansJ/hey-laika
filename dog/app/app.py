"""Flask API for one Bittle robot instance.

This service is the hardware/AI adapter for exactly ONE robot, identified by
Config.ROBOT_ID. All robot routes are scoped as /api/robots/<robot_id>/... and
validate that the id in the URL matches this instance — the Java orchestrator
addresses fleet members by routing to the right service.

There is no UI here; the orchestrator serves the frontend.
"""
import logging
import os
import threading
import time
from datetime import datetime, timezone
from wave import Error as wave_error
from functools import wraps

from flask import Flask, g, jsonify, request
from flask_cors import CORS

from pathlib import Path

from app.action_executor import execute_action
from app.bittle_controller import create_bittle_controller
from app.choreography import ChoreographyLibrary
from app.arbiter import Arbiter
from app.behavior_store import (PRIORITY_AGENT, PRIORITY_LIFECYCLE,
                                PRIORITY_MANUAL, BehaviorStore)
from app.ears import EarsService, build_transcriber
from app.event_binder import EventBinder
from app.eyes import EyesService, build_detector
from app.mood import MoodService
from app.mouth import MouthService
from app.ranger import RangerService
from app.satellite import SatelliteClient, SatelliteError
from app.gait_learner import GaitLearner
from app.leash import LeashService
from app.metrics import instrument_controller, metrics
from app.voice import (BEEP_PATTERNS, TtsNotConfiguredError, ollama_health,
                       play_beep, query_ollama, save_tts_audio,
                       synthesize_speech)
from app.config import Config
from app.models import init_db
from app.personality_engine import MissingCredentialsError, PersonalityEngine
from app.poll_policy import PollPolicy
from app.power import PowerTracker
from app.robot_schema import SERVO_LIMITS, build_schema
from app.senses import SensesService

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)

init_db()
bittle = create_bittle_controller()
metrics.init()
instrument_controller(bittle)
# Behavior framework: single arbiter owns all motion; lifecycle events
# (online/idle/battery/exception) flow through stored bindings. Wired
# BEFORE the first connect so startup counts as a came-online event.
behavior_store = BehaviorStore()
behavior_store.init()
arbiter = Arbiter(bittle, behavior_store)
# Adaptive polling: idle postures (rest/sit/lie) stretch dog-facing pings.
poll_policy = PollPolicy()
bittle.telemetry_ttl = poll_policy.telemetry_ttl
event_binder = EventBinder(arbiter, behavior_store, bittle,
                           battery_poll_s=poll_policy.battery_interval)
bittle.on_online = event_binder.on_online
bittle.on_output_line = event_binder.handle_output_line
# Proximity leash: consumes the firmware's event_rssi push; zone changes
# become leash.* events through the ordinary bindings.
leash = LeashService(bittle, event_binder)
# Senses layer: always-on odometry shadow + opportunistic WiFi sniffer.
# Away mode (leash enabled) suppresses sniffing — hotspot scans don't belong
# in the home map.
# Away mode (leash on) suppresses home-map sniffing — except for the rich
# mock, a GUI fixture that should produce BOTH leash and fingerprint data.
senses = SensesService(
    bittle, is_away=lambda: leash.enabled and not Config.MOCK_RICH)
senses.instrument(bittle)
senses.init()
# Power sessions: snapshot stats at power-on/off for battery-health trends
# and runtime prediction.
power = PowerTracker(bittle)
power.init()
# Ears: the XIAO satellite's microphone stream -> transcripts -> voice.phrase.
ears = EarsService(event_binder, transcriber=build_transcriber(),
                   sample_rate=Config.EARS_SAMPLE_RATE,
                   udp_port=Config.EARS_UDP_PORT,
                   wake_phrase=Config.WAKE_PHRASE,
                   energy_floor=Config.EARS_ENERGY_FLOOR)
if Config.EARS_ENABLED:
    ears.init()
# Mouth: host TTS -> 8 kHz PCM -> firmware PWM on the Grove Speaker Plus.
mouth = MouthService(bittle, Config.SPEAKER_PIN)
# Ultrasonic ranger on the UART socket: throttled one-shot reads.
ranger = RangerService(bittle, Config.ULTRASONIC_PIN)
# Satellite (camera + mood light) over HTTP; eyes and mood are inert
# without SATELLITE_HOST.
satellite = SatelliteClient(Config.SATELLITE_HOST, Config.SATELLITE_TIMEOUT_S)
eyes = EyesService(satellite, event_binder,
                   detector=build_detector(Config.EYES_MODEL, Config.EYES_CONFIDENCE),
                   fps=Config.EYES_FPS, enabled=Config.EYES_ENABLED)
eyes.init()
mood = MoodService(satellite, enabled=Config.MOOD_ENABLED)
mood.init()
event_binder.listeners.append(mood.on_event)


def _fan_out_event_frame(frame: dict) -> None:
    """Single dispatch point for unsolicited firmware event frames
    (event_rssi, event_us, event_exception, ...)."""
    leash.handle_event_frame(frame)
    kind = frame.get("type")
    if kind == "event_rssi":
        metrics.inc("ws.event_rssi")
    elif kind == "event_exception":
        # hey-laika firmware pushes IMU exceptions even while idle (the
        # EXCEPTION_REPORT line only rides along inside task results).
        metrics.inc("ws.event_exception")
        name = str(frame.get("name") or frame.get("code") or "?").lower()
        event_binder.handle_output_line(f"EXCEPTION_REPORT {name}")


class BadParam(ValueError):
    """A request parameter failed validation; becomes a 400."""


def _num_param(data: dict, key: str, default, lo=None, hi=None, kind=int):
    """Parse a numeric JSON field with bounds; raises BadParam on junk."""
    raw = data.get(key)
    if raw is None or raw == "":
        return default
    try:
        value = kind(raw)
    except (TypeError, ValueError):
        raise BadParam(f"'{key}' must be a {kind.__name__}")
    if lo is not None and value < lo:
        raise BadParam(f"'{key}' must be >= {lo}")
    if hi is not None and value > hi:
        raise BadParam(f"'{key}' must be <= {hi}")
    return value


@app.errorhandler(BadParam)
def _bad_param(exc):
    return jsonify({"error": "bad_request", "message": str(exc)}), 400


def _observe_for_poll_policy(original_send):
    def wrapped(command: str) -> bool:
        ok = original_send(command)
        if ok:
            poll_policy.observe_command(command)
        return ok
    return wrapped


bittle.send_command = _observe_for_poll_policy(bittle.send_command)


if hasattr(bittle, "on_event_frame"):
    bittle.on_event_frame = _fan_out_event_frame
if Config.MOCK_RICH:
    leash.set_enabled(True)  # GUI fixture: live zone data out of the box
# Env toggles are authoritative only when explicitly set; otherwise the DB
# (Behavior Lab edits) owns the enabled flags across restarts.
if "GREETING_ENABLED" in os.environ:
    behavior_store.set_binding_enabled("robot.online", "startup_greeting",
                                       Config.GREETING_ENABLED)
if "IDLE_ENABLED" in os.environ:
    behavior_store.set_binding_enabled("idle.timeout", "idle_sit",
                                       Config.IDLE_ENABLED)
    behavior_store.set_binding_enabled("idle.timeout", "idle_rest",
                                       Config.IDLE_ENABLED)
event_binder.start()
bittle.connect()
choreography = ChoreographyLibrary()
personality = PersonalityEngine()
gait_learner = GaitLearner(bittle)

# In-memory state surfaced to the orchestrator UI
_started_at = time.time()
_display_content = {"type": "text", "value": "Hello! I'm Bittle 🐕", "updatedAt": None}
_activity_log: list[dict] = []
_activity_lock = threading.Lock()


def log_activity(kind: str, message: str) -> None:
    with _activity_lock:
        _activity_log.append({
            "kind": kind,
            "message": message,
            "at": datetime.now(timezone.utc).isoformat(),
        })
        del _activity_log[:-100]


def set_display(value: str, content_type: str = "text") -> None:
    _display_content.update({
        "type": content_type,
        "value": value,
        "updatedAt": datetime.now(timezone.utc).isoformat(),
    })


def execute_animation(name: str) -> bool:
    frames = choreography.build_command_sequence(name)
    if not frames:
        return False
    for frame in frames:
        if not bittle.send_command(frame.command):
            logger.warning("Animation %s aborted: %s not acknowledged",
                           name, frame.command)
            return False
        # In mock mode don't actually sleep full durations; keep responses snappy.
        time.sleep(0.05 if Config.MOCK_MODE else frame.duration)
    personality.apply_behavior_effects(name)
    return True


class AutonomousLoop:
    def __init__(self):
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> bool:
        if self.running:
            return False
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        log_activity("autonomous", "Autonomous mode started")
        return True

    def stop(self) -> bool:
        if not self.running:
            return False
        self._stop.set()
        self._thread.join(timeout=3)
        log_activity("autonomous", "Autonomous mode stopped")
        return True

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                personality.tick()
                decision = personality.get_next_behavior(choreography.names())
                source = decision.get("source", "mock")
                log_activity("behavior",
                             f"[{source}] {decision['behavior']}: {decision['reason']}")
                set_display(f"{decision['behavior']} — {decision['reason']}")
                execute_animation(decision["behavior"])
            except MissingCredentialsError as exc:
                # Credentials won't fix themselves mid-loop — halt instead of
                # failing every interval.
                logger.error("Autonomous mode halted: %s", exc)
                log_activity("error", f"Autonomous mode halted: {exc}")
                set_display("Missing credentials — check ANTHROPIC_API_KEY in .env")
                self._stop.set()
                break
            except Exception:
                logger.exception("Autonomous loop iteration failed")
            self._stop.wait(Config.AUTONOMOUS_INTERVAL)


autonomous = AutonomousLoop()


def robot_scoped(fn):
    """Reject requests addressed to a robot this instance doesn't serve."""
    @wraps(fn)
    def wrapper(robot_id: str, *args, **kwargs):
        if robot_id != Config.ROBOT_ID:
            return jsonify({
                "error": "unknown_robot",
                "message": (f"Robot '{robot_id}' is not served here; "
                            f"this service handles '{Config.ROBOT_ID}'."),
            }), 404
        return fn(robot_id, *args, **kwargs)
    return wrapper


@app.errorhandler(MissingCredentialsError)
def handle_missing_credentials(exc):
    return jsonify({"error": "missing_credentials", "message": str(exc)}), 503


# ---------- Health (unscoped — used by Docker/orchestrator probes) ----------

# ---------- Metrics ----------

@app.before_request
def _metrics_start():
    g.metrics_t0 = time.time()


@app.after_request
def _metrics_end(response):
    start = getattr(g, "metrics_t0", None)
    # The rule is the route TEMPLATE (/api/robots/<robot_id>/...), so
    # cardinality stays bounded. /metrics itself is excluded — the
    # orchestrator polls it and would inflate its own numbers.
    if start is not None and request.url_rule and \
            request.url_rule.rule != "/metrics":
        key = f"http.{request.method} {request.url_rule.rule}"
        metrics.observe(key, (time.time() - start) * 1000.0,
                        ok=response.status_code < 500)
    return response


@app.get("/metrics")
def metrics_snapshot():
    # Battery rides along as a gauge: served from the controller's 40s
    # telemetry cache (no extra robot traffic), persisted forever by the
    # orchestrator's hourly rollups -> long-term discharge history.
    try:
        battery = bittle.get_telemetry().get("battery")
    except Exception:
        battery = None
    return jsonify({"robotId": Config.ROBOT_ID, "battery": battery,
                    **metrics.snapshot()})


@app.get("/api/health")
def health():
    return jsonify({
        "status": "healthy",
        "service": "bittle-python",
        "robotId": Config.ROBOT_ID,
        "environment": Config.ENVIRONMENT,
        "mockMode": Config.MOCK_MODE,
        "decisionEngine": Config.DECISION_ENGINE,
        "apiKeyConfigured": bool(Config.ANTHROPIC_API_KEY),
        "model": Config.decision_model(),
        "autonomous": autonomous.running,
    })


# ---------- Robot-scoped API ----------

@app.get("/api/robots/<robot_id>/status")
@robot_scoped
def robot_status(robot_id: str):
    hw = bittle.get_status()
    telemetry = bittle.get_telemetry()
    return jsonify({
        "robotId": robot_id,
        "connected": hw.get("connected", False),
        "mode": hw.get("mode"),
        "lastCommand": hw.get("last_command"),
        "commandsSent": hw.get("commands_sent"),
        "autonomous": autonomous.running,
        "mood": personality.get_state()["mood"],
        "battery": telemetry.get("battery"),
        "signal": telemetry.get("signal"),
        "uptimeSeconds": int(time.time() - _started_at),
        # Epoch of adapter start: the FE derives a smoothly ticking uptime
        # from this instead of re-rendering the polled integer.
        "startedAt": _started_at,
    })


@app.get("/api/robots/<robot_id>/power")
@robot_scoped
def robot_power(robot_id: str):
    return jsonify({"robotId": robot_id, **power.summary()})


@app.get("/api/robots/<robot_id>/polling")
@robot_scoped
def polling_status(robot_id: str):
    return jsonify({"robotId": robot_id, **poll_policy.status()})


@app.post("/api/robots/<robot_id>/polling")
@robot_scoped
def polling_config(robot_id: str):
    data = request.get_json(silent=True) or {}
    result = poll_policy.configure(data)
    log_activity("polling", f"poll policy updated: "
                            f"x{result['config']['idleMultiplier']} when idle")
    return jsonify({"robotId": robot_id, **result})


@app.get("/api/robots/<robot_id>/personality")
@robot_scoped
def robot_personality(robot_id: str):
    state = personality.get_state()
    return jsonify({
        "robotId": robot_id,
        "energy": state["energy"],
        "happiness": state["happiness"],
        "boredom": state["boredom"],
        "curiosity": state["curiosity"],
        "mood": state["mood"],
    })


@app.get("/api/robots/<robot_id>/behavior")
@robot_scoped
def robot_next_behavior(robot_id: str):
    decision = personality.get_next_behavior(choreography.names())
    log_activity("behavior",
                 f"[{decision.get('source', 'mock')}] {decision['behavior']}: {decision['reason']}")
    return jsonify({
        "robotId": robot_id,
        "behavior": decision["behavior"],
        "reason": decision["reason"],
        "source": decision.get("source", "mock"),
    })


@app.post("/api/robots/<robot_id>/command")
@robot_scoped
def robot_command(robot_id: str):
    data = request.get_json(silent=True) or {}
    command = data.get("command")
    if not command:
        return jsonify({"error": "bad_request", "message": "'command' is required"}), 400
    success = bittle.send_command(command)
    log_activity("command", f"Raw command: {command}")
    return jsonify({"robotId": robot_id, "command": command, "success": success})


@app.post("/api/robots/<robot_id>/interact/<interaction_type>")
@robot_scoped
def robot_interact(robot_id: str, interaction_type: str):
    try:
        state = personality.record_interaction(interaction_type)
    except ValueError as exc:
        return jsonify({"error": "bad_request", "message": str(exc)}), 400
    log_activity("interaction", f"User interaction: {interaction_type}")
    return jsonify({"robotId": robot_id, "interaction": interaction_type,
                    "personality": state})


@app.get("/api/robots/<robot_id>/choreography/list")
@robot_scoped
def robot_choreography_list(robot_id: str):
    return jsonify({"robotId": robot_id, "animations": choreography.list_animations()})


@app.post("/api/robots/<robot_id>/choreography/execute/<animation>")
@robot_scoped
def robot_choreography_execute(robot_id: str, animation: str):
    if not execute_animation(animation):
        return jsonify({"error": "not_found",
                        "message": f"Unknown animation: {animation}"}), 404
    log_activity("animation", f"Executed animation: {animation}")
    return jsonify({"robotId": robot_id, "animation": animation, "success": True})


@app.post("/api/robots/<robot_id>/autonomous/start")
@robot_scoped
def robot_autonomous_start(robot_id: str):
    changed = autonomous.start()
    return jsonify({"robotId": robot_id, "running": autonomous.running,
                    "changed": changed})


@app.post("/api/robots/<robot_id>/autonomous/stop")
@robot_scoped
def robot_autonomous_stop(robot_id: str):
    changed = autonomous.stop()
    return jsonify({"robotId": robot_id, "running": autonomous.running,
                    "changed": changed})


@app.get("/api/robots/<robot_id>/autonomous/status")
@robot_scoped
def robot_autonomous_status(robot_id: str):
    return jsonify({"robotId": robot_id, "running": autonomous.running,
                    "intervalSeconds": Config.AUTONOMOUS_INTERVAL})


@app.get("/api/robots/<robot_id>/schema")
@robot_scoped
def robot_schema(robot_id: str):
    info = bittle.get_info()
    return jsonify({
        "robotId": robot_id,
        "robotType": "bittle_x_v2",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "schema": build_schema(),
        "metadata": {
            "model": info.get("model"),
            "firmwareVersion": info.get("firmwareVersion"),
            "mode": bittle.get_status().get("mode"),
            # The orchestrator prices AI usage per model; it must know which
            # engine and model this adapter actually calls.
            "decisionEngine": Config.DECISION_ENGINE,
            "decisionModel": Config.decision_model(),
            "servoCount": len(SERVO_LIMITS),
            # Verified 2026-08-30: non-zero offsets stored in EEPROM. Do not
            # query 'c' live here — it physically moves the robot.
            "calibrated": True,
        },
    })


@app.get("/api/robots/<robot_id>/servo")
@robot_scoped
def robot_servo_read(robot_id: str):
    angles = bittle.read_joint_angles()
    if angles is None:
        return jsonify({"robotId": robot_id, "success": False,
                        "message": "Failed to read joint angles"}), 502
    return jsonify({
        "robotId": robot_id,
        "success": True,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        # Only physical joints; indices 1-7 are placeholders that report
        # garbage until a skill zeroes them.
        "joints": [{"index": i, "angle": angles[i]} for i in SERVO_LIMITS],
    })


@app.post("/api/robots/<robot_id>/servo")
@robot_scoped
def robot_servo_move(robot_id: str):
    if autonomous.running:
        return jsonify({"error": "autonomy_running",
                        "message": "Stop autonomous mode before manual servo "
                                   "control."}), 409
    data = request.get_json(silent=True) or {}
    joints = data.get("joints")
    if not isinstance(joints, list) or not joints:
        return jsonify({"error": "bad_request",
                        "message": "'joints' must be a non-empty list"}), 400
    moves: list[tuple[int, int]] = []
    clamped = False
    for joint in joints:
        try:
            index = int(joint["index"])
            angle = int(joint["angle"])
        except (KeyError, TypeError, ValueError):
            return jsonify({"error": "bad_request",
                            "message": "each joint needs integer 'index' and "
                                       "'angle'"}), 400
        limits = SERVO_LIMITS.get(index)
        if limits is None:
            return jsonify({"error": "bad_request",
                            "message": f"Invalid joint index {index}"}), 400
        lo, hi = limits
        safe = max(lo, min(hi, angle))
        if safe != angle:
            clamped = True
            logger.warning("Clamped joint %d: %d -> %d", index, angle, safe)
        moves.append((index, safe))
    success = bittle.move_joints(moves)
    log_activity("servo", "Servo move: " +
                 ", ".join(f"{i}->{a}°" for i, a in moves))
    return jsonify({
        "robotId": robot_id,
        "success": success,
        "clamped": clamped,
        "message": f"Moved {len(moves)} joint(s)" if success
                   else "Move failed (no completion echo)",
        "movedJoints": [{"index": i, "angle": a} for i, a in moves],
    }), (200 if success else 502)


@app.post("/api/robots/<robot_id>/execute_action")
@robot_scoped
def robot_execute_action(robot_id: str):
    """Phase 1b: the orchestrator's behavior loop drives the hardware here.

    The adapter's own autonomous loop is the deprecated old brain — running
    both would race on the servos, so this endpoint refuses while it's active.
    """
    if autonomous.running:
        return jsonify({"error": "autonomy_running",
                        "message": "Stop the adapter's autonomous loop before "
                                   "orchestrator-driven execution."}), 409
    data = request.get_json(silent=True) or {}
    action = data.get("action")
    if not action:
        return jsonify({"error": "bad_request",
                        "message": "'action' is required"}), 400
    duration_ms = _num_param(data, "durationMs", 0, lo=0,
                             hi=Config.MAX_ACTION_DURATION_MS)
    try:
        success, actual_ms, message = execute_action(bittle, action, duration_ms)
    except KeyError:
        return jsonify({"error": "bad_request",
                        "message": f"Unknown action: {action}"}), 400
    log_activity("action", f"[orchestrator] {action}: {message}")
    return jsonify({
        "robotId": robot_id,
        "action": action,
        "success": success,
        "actualDurationMs": actual_ms,
        "message": message,
    })


# ---------- Gait learning (autonomous IMU-based calibration) ----------

@app.post("/api/robots/<robot_id>/gait/start")
@robot_scoped
def gait_start(robot_id: str):
    """Start a learning session (moves the robot in supervised batches)."""
    if autonomous.running:
        return jsonify({"error": "autonomy_running",
                        "message": "Stop the autonomous loop first."}), 409
    data = request.get_json(silent=True) or {}
    sequence = data.get("sequence")
    if sequence is not None and (not isinstance(sequence, list) or
                                 not all(isinstance(c, str) for c in sequence)):
        return jsonify({"error": "bad_request",
                        "message": "'sequence' must be a list of command "
                                   "strings"}), 400
    started = gait_learner.start(
        sequence=sequence,
        iterations=_num_param(data, "iterations", 1, lo=1,
                              hi=Config.MAX_GAIT_ITERATIONS),
        batch_size=_num_param(data, "batchSize", 2, lo=1, hi=20),
        recenter=data.get("recenter") or "manual",
        verify_every=_num_param(data, "verifyEvery", 3, lo=1, hi=100),
        arena_half_m=_num_param(data, "arenaHalfM", 0.5, lo=0.1, hi=5.0,
                                kind=float))
    if not started:
        return jsonify({"error": "busy",
                        "message": "A learning session is already running"}), 409
    log_activity("gait", "Gait learning session started")
    return jsonify({"robotId": robot_id, "started": True,
                    "status": gait_learner.get_status()})


@app.get("/api/robots/<robot_id>/gait/status")
@robot_scoped
def gait_status(robot_id: str):
    return jsonify({"robotId": robot_id, **gait_learner.get_status()})


@app.post("/api/robots/<robot_id>/gait/continue")
@robot_scoped
def gait_continue(robot_id: str):
    """Operator confirms the robot is re-centered; next batch proceeds."""
    gait_learner.confirm_recenter()
    return jsonify({"robotId": robot_id, "status": gait_learner.get_status()})


@app.post("/api/robots/<robot_id>/gait/stop")
@robot_scoped
def gait_stop(robot_id: str):
    gait_learner.stop()
    log_activity("gait", "Gait learning session stopped")
    return jsonify({"robotId": robot_id, "status": gait_learner.get_status()})


@app.get("/api/robots/<robot_id>/gait/model")
@robot_scoped
def gait_model(robot_id: str):
    return jsonify({"robotId": robot_id, **gait_learner.get_model()})


# ---------- Behavior framework (single arbiter owns all motion) ----------

@app.get("/api/robots/<robot_id>/behaviors")
@robot_scoped
def behaviors_list(robot_id: str):
    return jsonify({"robotId": robot_id,
                    "behaviors": behavior_store.behaviors()})


@app.post("/api/robots/<robot_id>/behaviors")
@robot_scoped
def behaviors_upsert(robot_id: str):
    data = request.get_json(silent=True) or {}
    if not data.get("name") or not isinstance(data.get("steps"), list):
        return jsonify({"error": "bad_request",
                        "message": "'name' and 'steps' list required"}), 400
    data["cooldownS"] = _num_param(data, "cooldownS", 0, lo=0, hi=86400)
    return jsonify(behavior_store.upsert_behavior(data))


@app.get("/api/robots/<robot_id>/behaviors/<name>")
@robot_scoped
def behaviors_get(robot_id: str, name: str):
    behavior = behavior_store.behavior(name)
    if behavior is None:
        return jsonify({"error": "not_found"}), 404
    return jsonify(behavior)


@app.get("/api/robots/<robot_id>/bindings")
@robot_scoped
def bindings_list(robot_id: str):
    return jsonify({"robotId": robot_id,
                    "bindings": behavior_store.bindings()})


@app.post("/api/robots/<robot_id>/bindings")
@robot_scoped
def bindings_upsert(robot_id: str):
    data = request.get_json(silent=True) or {}
    if not data.get("event") or not data.get("behavior"):
        return jsonify({"error": "bad_request",
                        "message": "'event' and 'behavior' required"}), 400
    data["priority"] = _num_param(data, "priority", PRIORITY_LIFECYCLE,
                                  lo=1, hi=9)
    return jsonify(behavior_store.upsert_binding(data))


# ---- Senses layer ----

@app.get("/api/robots/<robot_id>/senses")
@robot_scoped
def senses_status(robot_id: str):
    return jsonify({"robotId": robot_id, **senses.status()})


@app.get("/api/robots/<robot_id>/senses/range")
@robot_scoped
def senses_range(robot_id: str):
    """One-shot ultrasonic read. The pin defaults to ULTRASONIC_PIN (set once
    the UART-socket wiring is known); ?pin=9|10 overrides for validation."""
    pin = _num_param(request.args, "pin", Config.ULTRASONIC_PIN, lo=0, hi=48)
    if not pin:
        return jsonify({"error": "not_configured",
                        "message": "ULTRASONIC_PIN is not set"}), 409
    reading = ranger.read(pin)
    return jsonify({"robotId": robot_id, **reading,
                    "recent": ranger.status()["recent"], **ranger.stats})


# ---- Mouth (host TTS -> firmware PWM -> Grove Speaker Plus) ----

@app.get("/api/robots/<robot_id>/mouth")
@robot_scoped
def mouth_status(robot_id: str):
    return jsonify({"robotId": robot_id, **mouth.status()})


@app.post("/api/robots/<robot_id>/mouth/say")
@robot_scoped
def mouth_say(robot_id: str):
    text = str((request.get_json(silent=True) or {}).get("text", "")).strip()
    if not text or len(text) > 400:
        return jsonify({"error": "bad_request",
                        "message": "'text' required (max 400 chars)"}), 400
    try:
        result = mouth.say(text)
    except RuntimeError as exc:
        return _speaker_error(exc)
    except Exception as exc:
        return jsonify({"error": "tts_failed", "message": str(exc)}), 502
    if mood.enabled and result.get("seconds"):
        mood.flash("speaking", float(result["seconds"]))
    log_activity("voice", f"Said: {text}")
    return jsonify({"robotId": robot_id, **result})


def _speaker_error(exc: RuntimeError):
    """SPEAKER_PIN unset is a configuration problem; a lost acknowledgement is
    the WiFi link to the dog dropping mid-clip (2026-09-04), not config."""
    if "not acknowledged" in str(exc) or "refused" in str(exc):
        return jsonify({"error": "speaker_unreachable", "message": str(exc)}), 502
    return jsonify({"error": "not_configured", "message": str(exc)}), 409


@app.post("/api/robots/<robot_id>/mouth/wav")
@robot_scoped
def mouth_wav(robot_id: str):
    """Play an uploaded PCM WAV (multipart field 'file'); arrival-day check
    of the speaker wiring without any TTS engine."""
    upload = request.files.get("file")
    if upload is None:
        return jsonify({"error": "bad_request", "message": "upload 'file'"}), 400
    try:
        result = mouth.play_wav(upload.read(), label=upload.filename or "wav")
    except RuntimeError as exc:
        return _speaker_error(exc)
    except (wave_error, EOFError, ValueError) as exc:
        return jsonify({"error": "bad_request", "message": str(exc)}), 400
    return jsonify({"robotId": robot_id, **result})


@app.get("/api/robots/<robot_id>/mouth/sounds")
@robot_scoped
def mouth_sounds(robot_id: str):
    return jsonify({"robotId": robot_id, "sounds": mouth.sounds.names(),
                    "enabled": mouth.enabled})


@app.post("/api/robots/<robot_id>/mouth/play")
@robot_scoped
def mouth_play(robot_id: str):
    """{"sound": "positive_bark"}: a library clip on the dog's speaker."""
    name = str((request.get_json(silent=True) or {}).get("sound", "")).strip()
    if not name:
        return jsonify({"error": "bad_request", "message": "'sound' required"}), 400
    try:
        result = mouth.play_sound(name)
    except KeyError as exc:
        return jsonify({"error": "bad_request", "message": str(exc.args[0])}), 400
    except RuntimeError as exc:
        return _speaker_error(exc)
    except Exception as exc:
        return jsonify({"error": "playback_failed", "message": str(exc)}), 502
    if mood.enabled and result.get("seconds"):
        mood.flash("speaking", float(result["seconds"]))
    log_activity("voice", f"Played sound: {name}")
    return jsonify({"robotId": robot_id, **result})


@app.post("/api/robots/<robot_id>/mouth/stop")
@robot_scoped
def mouth_stop(robot_id: str):
    return jsonify({"robotId": robot_id, "stopped": mouth.stop()})


# ---- Ears (XIAO satellite microphone -> whisper -> voice.phrase) ----

@app.get("/api/robots/<robot_id>/ears")
@robot_scoped
def ears_status(robot_id: str):
    return jsonify({"robotId": robot_id, **ears.status()})


@app.get("/api/robots/<robot_id>/ears/transcripts")
@robot_scoped
def ears_transcripts(robot_id: str):
    limit = _num_param(request.args, "limit", 20, lo=1, hi=200)
    return jsonify({"robotId": robot_id, "transcripts": ears.transcripts(limit)})


@app.post("/api/robots/<robot_id>/ears/record")
@robot_scoped
def ears_record(robot_id: str):
    """Console recorder: {"seconds": 3} captures the live mic for that long,
    transcribes it and reports the wake match without firing voice.phrase."""
    body = request.get_json(silent=True) or {}
    try:
        seconds = float(body.get("seconds", 3))
    except (TypeError, ValueError):
        return jsonify({"error": "bad_request", "message": "'seconds' must be a number"}), 400
    result = ears.record(seconds)
    log_activity("voice", f"Ears recorder: {result.get('text') or 'silence'}")
    return jsonify({"robotId": robot_id, **result})


@app.get("/api/robots/<robot_id>/ears/vocabulary")
@robot_scoped
def ears_vocabulary(robot_id: str):
    return jsonify({"robotId": robot_id, **ears.vocabulary_view()})


@app.post("/api/robots/<robot_id>/ears/vocabulary")
@robot_scoped
def ears_vocabulary_set(robot_id: str):
    """{"phrases": [...]} extra text whisper is primed with; {"variants": [...]}
    extra spellings accepted as the name after a leader ("hey", "okay", ...)."""
    body = request.get_json(silent=True) or {}
    try:
        return jsonify({"robotId": robot_id,
                        **ears.set_vocabulary(body.get("phrases"), body.get("variants"))})
    except ValueError as exc:
        return jsonify({"error": "bad_request", "message": str(exc)}), 400


@app.post("/api/robots/<robot_id>/ears/clip")
@robot_scoped
def ears_clip(robot_id: str):
    """Bench test without the satellite: upload a 16-bit mono WAV (multipart
    field 'file') or pass {"path": "<server-side wav>"}; runs the whole
    pipeline synchronously and returns the transcript row."""
    import tempfile

    upload = request.files.get("file")
    if upload is not None:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            upload.save(tmp.name)
            path = tmp.name
    else:
        path = (request.get_json(silent=True) or {}).get("path")
        if not path:
            return jsonify({"error": "bad_request",
                            "message": "upload 'file' or pass 'path'"}), 400
    try:
        row = ears.feed_wav(path)
    except (ValueError, OSError, wave_error) as exc:
        return jsonify({"error": "bad_request", "message": str(exc)}), 400
    log_activity("voice", f"Ears clip: {row['text'] if row else 'silence'}")
    return jsonify({"robotId": robot_id, "transcript": row})


# ---- Satellite: eyes (camera -> YOLO -> vision.*) and mood light ----

@app.get("/api/robots/<robot_id>/satellite")
@robot_scoped
def satellite_status(robot_id: str):
    """The XIAO's own status JSON (mic, camera, packets, rssi, led)."""
    if not satellite.enabled:
        return jsonify({"error": "not_configured",
                        "message": "SATELLITE_HOST is not set"}), 409
    try:
        return jsonify({"robotId": robot_id, **satellite.info(),
                        "device": satellite.status()})
    except SatelliteError as exc:
        return jsonify({"error": "satellite_unreachable", "message": str(exc),
                        **satellite.info()}), 502


@app.get("/api/robots/<robot_id>/eyes")
@robot_scoped
def eyes_status(robot_id: str):
    return jsonify({"robotId": robot_id, **eyes.status()})


@app.get("/api/robots/<robot_id>/eyes/snap")
@robot_scoped
def eyes_snap(robot_id: str):
    """The latest cached frame as image/jpeg (?fresh=1 fetches a new one)."""
    if request.args.get("fresh") == "1":
        try:
            eyes.capture()
        except SatelliteError as exc:
            return jsonify({"error": "satellite_unreachable", "message": str(exc)}), 502
    jpeg, at = eyes.frame()
    if jpeg is None:
        return jsonify({"error": "no_frame",
                        "message": "no frame received from the satellite yet"}), 404
    return app.response_class(jpeg, mimetype="image/jpeg", headers={
        "Cache-Control": "no-store", "X-Frame-At": str(at)})


@app.post("/api/robots/<robot_id>/eyes/config")
@robot_scoped
def eyes_config(robot_id: str):
    data = request.get_json(silent=True) or {}
    if "enabled" in data:
        try:
            eyes.set_enabled(bool(data["enabled"]))
        except RuntimeError as exc:
            return jsonify({"error": "not_configured", "message": str(exc)}), 409
        log_activity("eyes", f"Eyes {'enabled' if eyes.enabled else 'paused'}")
    return jsonify({"robotId": robot_id, **eyes.status()})


@app.post("/api/robots/<robot_id>/eyes/detect")
@robot_scoped
def eyes_detect(robot_id: str):
    """Bench test without the satellite: upload a JPEG (multipart field
    'file'); runs the detector synchronously, events included."""
    upload = request.files.get("file")
    if upload is None:
        return jsonify({"error": "bad_request", "message": "upload 'file'"}), 400
    jpeg = upload.read()
    if not jpeg.startswith(b"\xff\xd8"):
        return jsonify({"error": "bad_request", "message": "not a JPEG"}), 400
    try:
        persons = eyes.process(jpeg)
    except FileNotFoundError as exc:
        return jsonify({"error": "not_configured", "message": str(exc)}), 409
    return jsonify({"robotId": robot_id, "persons": persons,
                    "inferenceMs": eyes.stats["inferenceMs"]})


@app.get("/api/robots/<robot_id>/mood")
@robot_scoped
def mood_status(robot_id: str):
    return jsonify({"robotId": robot_id, **mood.status()})


@app.post("/api/robots/<robot_id>/mood")
@robot_scoped
def mood_set(robot_id: str):
    """{"mood": "happy"} pins a named mood; {"mood": "happy", "seconds": 3}
    flashes it; {"r","g","b","effect","periodMs","brightness"} pins a
    custom colour."""
    if not mood.enabled:
        return jsonify({"error": "not_configured",
                        "message": "SATELLITE_HOST is not set (or MOOD_ENABLED=false)"}), 409
    data = request.get_json(silent=True) or {}
    try:
        if data.get("mood"):
            seconds = _num_param(data, "seconds", None, lo=0.1, hi=600, kind=float)
            name = str(data["mood"])
            result = mood.flash(name, seconds) if seconds else mood.set(name)
            log_activity("mood", f"Mood {name}" + (f" for {seconds}s" if seconds else ""))
        else:
            result = mood.set_color(
                _num_param(data, "r", 0, lo=0, hi=255), _num_param(data, "g", 0, lo=0, hi=255),
                _num_param(data, "b", 0, lo=0, hi=255), str(data.get("effect", "solid")),
                _num_param(data, "periodMs", 1500, lo=100, hi=60000),
                _num_param(data, "brightness", 255, lo=0, hi=255))
            log_activity("mood", "Mood custom colour")
    except ValueError as exc:
        return jsonify({"error": "bad_request", "message": str(exc)}), 400
    if result.get("lastError"):
        return jsonify({"robotId": robot_id, **result}), 502
    return jsonify({"robotId": robot_id, **result})


@app.get("/api/robots/<robot_id>/senses/samples")
@robot_scoped
def senses_samples(robot_id: str):
    """Filtered slice of the fingerprint store for the map page.
    ?since= / ?until= are epoch seconds; ?every=N thins to one row in N;
    ?minAps= drops sparse scans; ?source=auto|manual."""
    args = request.args
    source = args.get("source") or None
    if source not in (None, "auto", "manual"):
        return jsonify({"error": "bad_request",
                        "message": "'source' must be auto or manual"}), 400
    result = senses.samples(
        limit=_num_param(args, "limit", 200, lo=1, hi=2000),
        since=_num_param(args, "since", None, lo=0, kind=float),
        until=_num_param(args, "until", None, lo=0, kind=float),
        source=source,
        min_aps=_num_param(args, "minAps", 0, lo=0, hi=100),
        every=_num_param(args, "every", 1, lo=1, hi=1000))
    return jsonify({"robotId": robot_id, "pose": senses.pose(), **result})


@app.post("/api/robots/<robot_id>/senses/pose/reset")
@robot_scoped
def senses_pose_reset(robot_id: str):
    """Re-anchor the dead-reckoned origin (dog placed at its home spot)."""
    data = request.get_json(silent=True) or {}
    heading = _num_param(data, "heading", 0.0, lo=-180, hi=180, kind=float)
    log_activity("senses", "Pose reset to origin")
    return jsonify({"robotId": robot_id, "pose": senses.reset_pose(heading)})


@app.post("/api/robots/<robot_id>/senses/sniff")
@robot_scoped
def senses_sniff(robot_id: str):
    """Manual sniff (ignores the politeness clock; still one blocking scan)."""
    sample = senses.sniff(source="manual")
    if sample is None:
        return jsonify({"error": "scan_failed",
                        "message": "no scan data (transport can't capture "
                                   "output, or no APs visible)"}), 502
    return jsonify({"robotId": robot_id, "sample": sample})


# ---- Proximity leash ----

@app.get("/api/robots/<robot_id>/leash")
@robot_scoped
def leash_status(robot_id: str):
    return jsonify({"robotId": robot_id, **leash.status()})


@app.post("/api/robots/<robot_id>/leash/config")
@robot_scoped
def leash_config(robot_id: str):
    data = request.get_json(silent=True) or {}
    if "enabled" in data:
        leash.set_enabled(bool(data["enabled"]))
    leash.configure(data)
    log_activity("leash", f"leash config: enabled={leash.enabled}")
    return jsonify({"robotId": robot_id, **leash.status()})


@app.post("/api/robots/<robot_id>/leash/mark")
@robot_scoped
def leash_mark(robot_id: str):
    data = request.get_json(silent=True) or {}
    label = str(data.get("label") or "mark")
    entry = leash.mark(label)
    return jsonify({"robotId": robot_id, "mark": entry, **leash.status()})


@app.get("/api/robots/<robot_id>/arbiter/status")
@robot_scoped
def arbiter_status(robot_id: str):
    return jsonify({"robotId": robot_id, **arbiter.status()})


@app.post("/api/robots/<robot_id>/arbiter/invoke")
@robot_scoped
def arbiter_invoke(robot_id: str):
    data = request.get_json(silent=True) or {}
    name = data.get("behavior")
    if not name:
        return jsonify({"error": "bad_request",
                        "message": "'behavior' required"}), 400
    source = data.get("source", "manual")
    priority = _num_param(
        data, "priority",
        PRIORITY_AGENT if source == "agent" else PRIORITY_MANUAL, lo=1, hi=9)
    if source == "agent":
        cause = {"type": "agent", "decisionId": data.get("decisionId")}
    else:
        cause = {"type": "manual", "via": data.get("via", "api")}
    event_binder.reset_idle()
    result = arbiter.submit(name, source=source, priority=priority, cause=cause)
    log_activity("behavior", f"invoke {name} ({source}): {result['status']}")
    return jsonify({"robotId": robot_id, "behavior": name, **result})


@app.post("/api/robots/<robot_id>/arbiter/stop")
@robot_scoped
def arbiter_stop(robot_id: str):
    return jsonify({"robotId": robot_id, **arbiter.stop_current()})


@app.post("/api/robots/<robot_id>/abort")
@robot_scoped
def robot_abort(robot_id: str):
    """Emergency stop: interrupt the arbiter's current behavior and ask the
    firmware (hey-laika abort frame) to drop its queue and rest now."""
    stopped = arbiter.stop_current()
    aborted = bittle.abort()
    event_binder.reset_idle()
    log_activity("safety", f"Abort requested (firmware ack: {aborted})")
    return jsonify({"robotId": robot_id, "aborted": aborted,
                    "arbiter": stopped})


# ---- Back-compat shims: the /greeting and /idle endpoints the GUI already
# uses, reimplemented on the framework (greeting.py/idle_keeper.py retired).

def _greeting_shim() -> dict:
    behavior = behavior_store.behavior("startup_greeting") or {"steps": []}
    bindings = behavior_store.bindings(event="robot.online")
    enabled = any(b["enabled"] and b["behavior"] == "startup_greeting"
                  for b in bindings)
    runs = [r for r in behavior_store.recent_runs(50)
            if r["behavior"] == "startup_greeting" and r["status"] != "running"]
    return {"enabled": enabled, "runs": len(runs),
            "lastResult": ("ok" if runs and runs[0]["status"] == "complete"
                           else (runs[0]["status"] if runs else None)),
            "trigger": "robot comes online (binding: robot.online)",
            "sequence": behavior["steps"]}


def _idle_shim() -> dict:
    bindings = [b for b in behavior_store.bindings(event="idle.timeout")]
    thresholds = sorted(float((b.get("filter") or {}).get("seconds", 0))
                        for b in bindings) or [0, 0]
    idle_runs = [r for r in behavior_store.recent_runs(20)
                 if r["behavior"].startswith("idle_")]
    state = "active"
    if idle_runs and idle_runs[0]["status"] == "complete":
        state = "lying" if idle_runs[0]["behavior"] == "idle_rest" else "sitting"
    return {"enabled": any(b["enabled"] for b in bindings), "state": state,
            "sitAfterS": thresholds[0], "restAfterS": thresholds[-1],
            "transitions": len(idle_runs)}


@app.get("/api/robots/<robot_id>/greeting")
@robot_scoped
def greeting_status(robot_id: str):
    return jsonify({"robotId": robot_id, **_greeting_shim()})


@app.post("/api/robots/<robot_id>/greeting/run")
@robot_scoped
def greeting_run(robot_id: str):
    result = arbiter.submit("startup_greeting", source="manual",
                            priority=PRIORITY_MANUAL,
                            cause={"type": "manual", "via": "greeting"})
    log_activity("greeting", f"Go-mode greeting: {result['status']}")
    return jsonify({"robotId": robot_id,
                    "started": result["status"] != "rejected", **result})


@app.post("/api/robots/<robot_id>/greeting/enable")
@robot_scoped
def greeting_enable(robot_id: str):
    behavior_store.set_binding_enabled("robot.online", "startup_greeting", True)
    return jsonify({"robotId": robot_id, **_greeting_shim()})


@app.post("/api/robots/<robot_id>/greeting/disable")
@robot_scoped
def greeting_disable(robot_id: str):
    behavior_store.set_binding_enabled("robot.online", "startup_greeting", False)
    return jsonify({"robotId": robot_id, **_greeting_shim()})


@app.get("/api/robots/<robot_id>/idle")
@robot_scoped
def idle_status(robot_id: str):
    return jsonify({"robotId": robot_id, **_idle_shim()})


@app.post("/api/robots/<robot_id>/idle/enable")
@robot_scoped
def idle_enable(robot_id: str):
    behavior_store.set_binding_enabled("idle.timeout", "idle_sit", True)
    behavior_store.set_binding_enabled("idle.timeout", "idle_rest", True)
    return jsonify({"robotId": robot_id, **_idle_shim()})


@app.post("/api/robots/<robot_id>/idle/disable")
@robot_scoped
def idle_disable(robot_id: str):
    behavior_store.set_binding_enabled("idle.timeout", "idle_sit", False)
    behavior_store.set_binding_enabled("idle.timeout", "idle_rest", False)
    return jsonify({"robotId": robot_id, **_idle_shim()})


# ---------- Voice ("Hey Laika") — MVP with stubbed audio I/O ----------

@app.post("/api/robots/<robot_id>/sound")
@robot_scoped
def robot_sound(robot_id: str):
    """Buzzer feedback patterns (wake-word / recording / processing / ready)."""
    data = request.get_json(silent=True) or {}
    pattern = data.get("pattern", "beep_wake_word")
    if pattern not in BEEP_PATTERNS:
        return jsonify({"error": "bad_request",
                        "message": f"Unknown pattern '{pattern}'; one of "
                                   f"{sorted(BEEP_PATTERNS)}"}), 400
    success = play_beep(bittle, pattern)
    return jsonify({"robotId": robot_id, "pattern": pattern,
                    "command": BEEP_PATTERNS[pattern], "success": success})


@app.get("/api/robots/<robot_id>/voice/health")
@robot_scoped
def robot_voice_health(robot_id: str):
    return jsonify({
        "robotId": robot_id,
        "ollama": ollama_health(),
        "ttsConfigured": bool(Config.ELEVENLABS_API_KEY),
        "microphone": "stubbed (text input via /voice/demo)",
        "speaker": "stubbed (buzzer beeps + optional TTS file)",
    })


@app.post("/api/robots/<robot_id>/voice/demo")
@robot_scoped
def robot_voice_demo(robot_id: str):
    """End-to-end voice chain without hardware: text in, LLM reply out.

    Stubs: wake-word + recording are simulated (buzzer feedback only) and the
    input text stands in for a Whisper transcription. Real: local Ollama, the
    buzzer, and (optionally, with an API key) Eleven Labs TTS.
    """
    started = time.time()
    data = request.get_json(silent=True) or {}
    user_input = (data.get("input") or "").strip()
    if not user_input:
        return jsonify({"error": "bad_request",
                        "message": "'input' is required"}), 400

    wake_start = time.time()
    play_beep(bittle, "beep_wake_word")      # [STUB] wake-word detected
    wake_time = time.time() - wake_start

    record_start = time.time()
    play_beep(bittle, "recording")           # [STUB] recording
    record_time = time.time() - record_start

    ollama_start = time.time()
    response_text, error = query_ollama(
        user_input,
        model=data.get("model"),
        temperature=_num_param(data, "temperature", 0.7, lo=0.0, hi=2.0,
                               kind=float))
    ollama_time = time.time() - ollama_start
    if error:
        log_activity("voice", f"Voice demo failed: {error}")
        return jsonify({"status": "error", "error": "llm_unavailable",
                        "message": error}), 502

    audio_url = None
    tts_time = 0.0
    tts_error = None
    if data.get("use_tts"):
        tts_start = time.time()
        try:
            audio_url = save_tts_audio(synthesize_speech(response_text),
                                       Path(app.static_folder))
        except TtsNotConfiguredError as exc:
            tts_error = str(exc)
        except Exception as exc:
            tts_error = f"TTS failed: {exc}"
        tts_time = time.time() - tts_start

    play_beep(bittle, "ready")
    log_activity("voice", f"Voice: '{user_input[:60]}' -> "
                          f"'{response_text[:60]}'")
    set_display(response_text)

    return jsonify({
        "status": "success",
        "robotId": robot_id,
        "userInput": user_input,
        "transcribedText": user_input,     # stub: no Whisper yet
        "response": response_text,
        "model": data.get("model") or Config.OLLAMA_MODEL,
        "audioUrl": audio_url,
        "ttsError": tts_error,
        "latencySec": {
            "wakeWord": round(wake_time, 2),
            "recording": round(record_time, 2),
            "ollama": round(ollama_time, 2),
            "tts": round(tts_time, 2),
            "total": round(time.time() - started, 2),
        },
    })


@app.post("/api/robots/<robot_id>/voice/speak")
@robot_scoped
def robot_voice_speak(robot_id: str):
    """Standalone TTS: text -> MP3 under /static/responses/."""
    data = request.get_json(silent=True) or {}
    text = (data.get("text") or "").strip()
    if not text:
        return jsonify({"error": "bad_request",
                        "message": "'text' is required"}), 400
    try:
        audio_url = save_tts_audio(synthesize_speech(text),
                                   Path(app.static_folder))
    except TtsNotConfiguredError as exc:
        return jsonify({"error": "tts_not_configured", "message": str(exc)}), 503
    except Exception as exc:
        return jsonify({"error": "tts_failed", "message": str(exc)}), 502
    return jsonify({"robotId": robot_id, "status": "success",
                    "audioUrl": audio_url})


@app.get("/api/robots/<robot_id>/activity")
@robot_scoped
def robot_activity(robot_id: str):
    with _activity_lock:
        return jsonify({"robotId": robot_id, "activity": list(reversed(_activity_log))})


@app.get("/api/robots/<robot_id>/display")
@robot_scoped
def robot_display(robot_id: str):
    return jsonify({"robotId": robot_id, **_display_content})


if __name__ == "__main__":
    app.run(host=Config.HOST, port=5000, debug=Config.DEBUG,
            use_reloader=False)
