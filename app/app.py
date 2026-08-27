"""Main Flask application for the Bittle AI Companion."""
import logging
import threading
import time
from datetime import datetime, timezone

from flask import Flask, jsonify, render_template, request
from flask_cors import CORS

from app.bittle_controller import create_bittle_controller
from app.choreography import ChoreographyLibrary
from app.config import Config
from app.models import init_db
from app.personality_engine import PersonalityEngine

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

app = Flask(__name__, template_folder="../templates", static_folder="../static")
CORS(app)

init_db()
bittle = create_bittle_controller()
bittle.connect()
choreography = ChoreographyLibrary()
personality = PersonalityEngine()

# In-memory state shared with the display page and the activity log
_display_content = {"type": "text", "value": "Hello! I'm Bittle 🐕", "updated_at": None}
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
        "updated_at": datetime.now(timezone.utc).isoformat(),
    })


def execute_animation(name: str) -> bool:
    frames = choreography.build_command_sequence(name)
    if not frames:
        return False
    for frame in frames:
        bittle.send_command(frame.command)
        # In mock mode don't actually sleep full durations; keep the UI snappy.
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
            except Exception:
                logger.exception("Autonomous loop iteration failed")
            self._stop.wait(Config.AUTONOMOUS_INTERVAL)


autonomous = AutonomousLoop()


# ---------- Health & status ----------

@app.get("/api/health")
def health():
    return jsonify({
        "status": "healthy",
        "bittle": bittle.get_status(),
        "personality": personality.get_state(),
        "autonomous": autonomous.running,
        "environment": Config.ENVIRONMENT,
        "mock_mode": Config.MOCK_MODE,
        "llm_enabled": Config.llm_enabled(),
        "model": Config.CLAUDE_MODEL if Config.llm_enabled() else None,
    })


@app.get("/api/personality")
def get_personality():
    return jsonify(personality.get_state())


@app.get("/bittle/status")
def bittle_status():
    return jsonify(bittle.get_status())


# ---------- Behavior ----------

@app.get("/api/personality/behavior")
def next_behavior():
    decision = personality.get_next_behavior(choreography.names())
    log_activity("behavior",
                 f"[{decision.get('source', 'mock')}] {decision['behavior']}: {decision['reason']}")
    return jsonify(decision)


@app.post("/api/personality/interact/<interaction_type>")
def interact(interaction_type: str):
    try:
        state = personality.record_interaction(interaction_type)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    log_activity("interaction", f"User interaction: {interaction_type}")
    return jsonify({"ok": True, "personality": state})


@app.get("/api/choreography/list")
def list_choreography():
    return jsonify(choreography.list_animations())


@app.post("/api/choreography/execute/<animation>")
def run_choreography(animation: str):
    if not execute_animation(animation):
        return jsonify({"error": f"Unknown animation: {animation}"}), 404
    log_activity("animation", f"Executed animation: {animation}")
    return jsonify({"ok": True, "animation": animation})


# ---------- Autonomous mode ----------

@app.post("/api/autonomous/start")
def autonomous_start():
    started = autonomous.start()
    return jsonify({"running": autonomous.running, "changed": started})


@app.post("/api/autonomous/stop")
def autonomous_stop():
    stopped = autonomous.stop()
    return jsonify({"running": autonomous.running, "changed": stopped})


@app.get("/api/autonomous/status")
def autonomous_status():
    return jsonify({"running": autonomous.running,
                    "interval_seconds": Config.AUTONOMOUS_INTERVAL})


# ---------- Activity log & display ----------

@app.get("/api/activity")
def activity():
    with _activity_lock:
        return jsonify(list(reversed(_activity_log)))


@app.get("/current")
def current_display():
    return jsonify(_display_content)


# ---------- Web UI ----------

@app.get("/")
def dashboard():
    return render_template("dashboard.html")


@app.get("/display")
def display():
    return render_template("display.html")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=Config.DEBUG, use_reloader=False)
