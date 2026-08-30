"""Flask API for one Bittle robot instance.

This service is the hardware/AI adapter for exactly ONE robot, identified by
Config.ROBOT_ID. All robot routes are scoped as /api/robots/<robot_id>/... and
validate that the id in the URL matches this instance — the Java orchestrator
addresses fleet members by routing to the right service.

There is no UI here; the orchestrator serves the frontend.
"""
import logging
import threading
import time
from datetime import datetime, timezone
from functools import wraps

from flask import Flask, jsonify, request
from flask_cors import CORS

from app.action_executor import execute_action
from app.bittle_controller import create_bittle_controller
from app.choreography import ChoreographyLibrary
from app.config import Config
from app.models import init_db
from app.personality_engine import MissingCredentialsError, PersonalityEngine
from app.robot_schema import SERVO_LIMITS, build_schema

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)

init_db()
bittle = create_bittle_controller()
bittle.connect()
choreography = ChoreographyLibrary()
personality = PersonalityEngine()

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
        bittle.send_command(frame.command)
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
        "model": Config.CLAUDE_MODEL if Config.claude_engine() else None,
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
    })


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
    try:
        duration_ms = int(data.get("durationMs") or 0)
    except (TypeError, ValueError):
        return jsonify({"error": "bad_request",
                        "message": "'durationMs' must be an integer"}), 400
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
    app.run(host="0.0.0.0", port=5000, debug=Config.DEBUG, use_reloader=False)
