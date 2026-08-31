"""Host-managed lifecycle behavior: the "go mode" boot greeting.

Firmware is a silent machine after the hey-laika reset; ALL personality
lives host-side. When the robot transitions offline -> online, the adapter
runs this greeting: stand, stretch, a cheerful "ready" jingle, settle.

Driver rules honored (docs/reports/CALIBRATION_2026-08-31.md):
- interleave kup between bounded/skill gaits (tolerate its no-op failure)
- command completion echoes are immediate; wall-clock waits between steps
"""
import logging
import threading
import time

logger = logging.getLogger(__name__)

# Cheerful ascending "go mode" jingle: note/duration pairs for the buzzer.
GO_JINGLE = "b 14 8 18 8 21 8 26 4"

DEBOUNCE_S = 60.0

# (command, settle seconds) — stretch is a one-shot behavior skill.
SEQUENCE = [
    ("kup", 2.5),
    ("kstr", 5.0),
    ("kup", 2.0),
    (GO_JINGLE, 1.5),
    ("kbalance", 2.0),
]


class BootGreeter:
    def __init__(self, controller, enabled: bool = True):
        self.controller = controller
        self.enabled = enabled
        self._lock = threading.Lock()
        self._last_run = 0.0
        self.runs = 0
        self.last_result: str | None = None

    def on_online(self) -> None:
        """Controller callback: robot just became reachable."""
        if not self.enabled:
            return
        with self._lock:
            if time.time() - self._last_run < DEBOUNCE_S:
                return
            self._last_run = time.time()
        self.run()

    def run(self) -> bool:
        """Execute the greeting sequence (blocking; call from a thread)."""
        logger.info("Boot greeting: robot online — running go-mode sequence")
        ok = True
        for command, settle in SEQUENCE:
            sent = self.controller.send_command(command)
            if not sent and command != "kup":  # kup no-ops report failure
                ok = False
                logger.warning("Greeting step failed: %s", command)
            time.sleep(settle)
        with self._lock:
            self.runs += 1
            self.last_result = "ok" if ok else "partial"
        logger.info("Boot greeting complete (%s)", self.last_result)
        return ok

    def status(self) -> dict:
        with self._lock:
            return {"enabled": self.enabled, "runs": self.runs,
                    "lastResult": self.last_result,
                    "trigger": "robot comes online (debounced 60s)",
                    "sequence": [{"command": c, "settleS": s}
                                 for c, s in SEQUENCE]}
