"""Test configuration: force mock mode and an isolated throwaway database."""
import os
import tempfile

os.environ["MOCK_MODE"] = "True"
os.environ["DECISION_ENGINE"] = "mock"
os.environ["ANTHROPIC_API_KEY"] = ""
os.environ["SQLITE_DB_PATH"] = os.path.join(tempfile.mkdtemp(), "test_bittle.db")
# The mock controller ray-casts a simulated room, so the ranger is live.
os.environ["ULTRASONIC_PIN"] = "9"
