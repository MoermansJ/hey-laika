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
    DEBUG = _bool("DEBUG", True)

    # Identity: which robot instance this service is the adapter for. The
    # orchestrator addresses services by this id; requests for any other id
    # are rejected with 404.
    ROBOT_ID = os.getenv("ROBOT_ID", "bittle-1").strip()

    # Hardware
    MOCK_MODE = _bool("MOCK_MODE", True)
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
