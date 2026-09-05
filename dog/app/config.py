"""Environment-based configuration for the Bittle AI Companion."""
import os
from pathlib import Path

from dotenv import load_dotenv

# Load .env from the project root regardless of the working directory.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")


def _bool(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).strip().lower() in ("1", "true", "yes", "on")


class Config:
    ENVIRONMENT = os.getenv("ENVIRONMENT", "development")
    # DEBUG=True exposes the Werkzeug interactive debugger to anyone who can
    # reach the port; it is opt-in only. HOST defaults to loopback for the
    # native `python -m app.app` run; Docker (gunicorn) binds 0.0.0.0 itself.
    DEBUG = _bool("DEBUG", False)
    HOST = os.getenv("HOST", "127.0.0.1").strip()

    # Request caps: a huge durationMs would pin a worker thread for hours.
    MAX_ACTION_DURATION_MS = int(os.getenv("MAX_ACTION_DURATION_MS", "60000"))
    MAX_GAIT_ITERATIONS = int(os.getenv("MAX_GAIT_ITERATIONS", "20"))

    # Identity: which robot instance this service is the adapter for. The
    # orchestrator addresses services by this id; requests for any other id
    # are rejected with 404.
    ROBOT_ID = os.getenv("ROBOT_ID", "bittle-1").strip()

    # Hardware
    MOCK_MODE = _bool("MOCK_MODE", True)
    # MOCK_RICH: the mock controller also synthesizes the firmware's push
    # surfaces (event_rssi walk, XWs fingerprint scans) and auto-enables the
    # leash — a GUI-development fixture with live-looking data.
    MOCK_RICH = _bool("MOCK_RICH", False)
    BITTLE_COMMUNICATION_METHOD = os.getenv("BITTLE_COMMUNICATION_METHOD", "mock")
    BITTLE_SERIAL_PORT = os.getenv("BITTLE_SERIAL_PORT", "COM3")
    BITTLE_SERIAL_BAUD = int(os.getenv("BITTLE_SERIAL_BAUD", "115200"))
    BITTLE_WIFI_HOST = os.getenv("BITTLE_WIFI_HOST", "192.168.0.246")
    BITTLE_WIFI_PORT = int(os.getenv("BITTLE_WIFI_PORT", "81"))

    # AI decision engine
    # DECISION_ENGINE: "ollama" (default) decides via the local model — zero
    # cost, offline-capable; "claude" requires ANTHROPIC_API_KEY and raises
    # MissingCredentialsError without it; "mock" is an explicit offline opt-in.
    DECISION_ENGINE = os.getenv("DECISION_ENGINE", "ollama").strip().lower()
    ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "").strip()
    CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-opus-5")

    # Voice feature ("Hey Laika") — local LLM + optional TTS
    OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434").rstrip("/")
    # Lightest workable model, deliberately temporary; swap via env when the
    # voice hardware arrives and quality starts to matter (e.g. mistral).
    OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2:1b")
    OLLAMA_TIMEOUT = int(os.getenv("OLLAMA_TIMEOUT", "60"))
    ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "").strip()
    ELEVENLABS_VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM")

    # Database
    DATABASE_TYPE = os.getenv("DATABASE_TYPE", "sqlite")
    SQLITE_DB_PATH = os.getenv("SQLITE_DB_PATH", "./bittle.db")
    DATABASE_URL = os.getenv("DATABASE_URL", "")  # set for postgres in production

    # Persistence toggles
    PERSISTENCE_ENABLED = _bool("PERSISTENCE_ENABLED", True)
    SAVE_CONVERSATION_HISTORY = _bool("SAVE_CONVERSATION_HISTORY", True)
    SAVE_BEHAVIOR_LOG = _bool("SAVE_BEHAVIOR_LOG", True)

    # Autonomous loop
    AUTONOMOUS_INTERVAL = int(os.getenv("AUTONOMOUS_INTERVAL", "15"))

    # Host-managed lifecycle behavior: greet (stretch + jingle) when the
    # robot comes online. Firmware is silent; personality lives here.
    GREETING_ENABLED = _bool("GREETING_ENABLED", True)

    # Ears: PCM from the XIAO satellite over UDP -> whisper -> voice.phrase.
    EARS_ENABLED = _bool("EARS_ENABLED", True)
    EARS_UDP_PORT = int(os.getenv("EARS_UDP_PORT", "5005"))
    EARS_SAMPLE_RATE = int(os.getenv("EARS_SAMPLE_RATE", "16000"))
    EARS_ENERGY_FLOOR = int(os.getenv("EARS_ENERGY_FLOOR", "300"))
    WAKE_PHRASE = os.getenv("WAKE_PHRASE", "hey laika")
    WHISPER_MODEL = os.getenv("WHISPER_MODEL", "base")
    # Conversation: "Hey Laika" -> listen -> LLM router -> behavior and/or speech.
    CONVERSATION_ENABLED = _bool("CONVERSATION_ENABLED", True)
    CONVERSATION_LISTEN_S = float(os.getenv("CONVERSATION_LISTEN_S", "8"))
    CONVERSATION_REPLY_CHARS = int(os.getenv("CONVERSATION_REPLY_CHARS", "320"))
    WHISPER_CACHE = os.getenv("WHISPER_CACHE", "")

    # Ultrasonic ranger on the UART socket: which GPIO took the SIG wire
    # (9 or 10) is only known once wired; None disables range reads.
    ULTRASONIC_PIN = int(os.getenv("ULTRASONIC_PIN", "0")) or None
    # Grove Speaker Plus on the other UART-socket pin (firmware PWM playback).
    SPEAKER_PIN = int(os.getenv("SPEAKER_PIN", "0")) or None

    # XIAO satellite (camera + mood light) reached over HTTP on its own WiFi
    # address; empty = no satellite (eyes and mood report disabled).
    SATELLITE_HOST = os.getenv("SATELLITE_HOST", "").strip()
    SATELLITE_TIMEOUT_S = float(os.getenv("SATELLITE_TIMEOUT_S", "2.5"))

    # Eyes: satellite JPEG frames -> YOLOv8n (onnxruntime) -> vision.person.
    EYES_ENABLED = _bool("EYES_ENABLED", True)
    EYES_FPS = float(os.getenv("EYES_FPS", "4"))
    EYES_MODEL = os.getenv("EYES_MODEL",
                           str(PROJECT_ROOT / "models" / "yolov8n.onnx"))
    EYES_CONFIDENCE = float(os.getenv("EYES_CONFIDENCE", "0.45"))

    # Mood light: the chainable RGB LED on the satellite (mood.py).
    MOOD_ENABLED = _bool("MOOD_ENABLED", True)

    # Idle ladder: stationary > sit threshold -> sit; > rest threshold -> lie.
    IDLE_ENABLED = _bool("IDLE_ENABLED", True)
    IDLE_SIT_S = float(os.getenv("IDLE_SIT_S", "60"))
    IDLE_REST_S = float(os.getenv("IDLE_REST_S", "120"))

    @classmethod
    def sqlalchemy_url(cls) -> str:
        if cls.DATABASE_TYPE == "postgres" and cls.DATABASE_URL:
            return cls.DATABASE_URL
        db_path = Path(cls.SQLITE_DB_PATH)
        if not db_path.is_absolute():
            db_path = PROJECT_ROOT / db_path
        return f"sqlite:///{db_path.as_posix()}"

    @classmethod
    def claude_engine(cls) -> bool:
        return cls.DECISION_ENGINE == "claude"

    @classmethod
    def decision_model(cls) -> str | None:
        return {"claude": cls.CLAUDE_MODEL,
                "ollama": cls.OLLAMA_MODEL}.get(cls.DECISION_ENGINE)
