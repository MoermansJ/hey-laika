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

    # Hardware
    MOCK_MODE = _bool("MOCK_MODE", True)
    BITTLE_COMMUNICATION_METHOD = os.getenv("BITTLE_COMMUNICATION_METHOD", "mock")
    BITTLE_SERIAL_PORT = os.getenv("BITTLE_SERIAL_PORT", "COM3")
    BITTLE_WIFI_HOST = os.getenv("BITTLE_WIFI_HOST", "192.168.1.100")

    # Claude
    ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "").strip()
    CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-opus-5")

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

    @classmethod
    def sqlalchemy_url(cls) -> str:
        if cls.DATABASE_TYPE == "postgres" and cls.DATABASE_URL:
            return cls.DATABASE_URL
        db_path = Path(cls.SQLITE_DB_PATH)
        if not db_path.is_absolute():
            db_path = PROJECT_ROOT / db_path
        return f"sqlite:///{db_path.as_posix()}"

    @classmethod
    def llm_enabled(cls) -> bool:
        """Claude is used only when a key is present; otherwise mock decisions."""
        return bool(cls.ANTHROPIC_API_KEY)
