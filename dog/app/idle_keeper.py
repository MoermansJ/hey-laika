"""Host-managed idle behavior: the robot settles when nothing is happening.

Stationary > sit_after seconds -> sit; > rest_after seconds -> lie down.
Any external motion command resets the ladder. The keeper's own posture
commands are excluded from the activity clock, and it suppresses itself
while another driver (gait learner, autonomous loop) owns the robot.
"""
import logging
import threading
import time

logger = logging.getLogger(__name__)


class IdleKeeper:
    ACTIVE, SITTING, LYING = "active", "sitting", "lying"

    def __init__(self, controller, enabled: bool = True,
                 sit_after_s: float = 60.0, rest_after_s: float = 120.0,
                 tick_s: float = 5.0, suppressed=None):
        self.controller = controller
        self.enabled = enabled
        self.sit_after_s = sit_after_s
        self.rest_after_s = rest_after_s
        self.tick_s = tick_s
        self.suppressed = suppressed or (lambda: False)
        self.state = self.ACTIVE
        self.transitions = 0
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _settle(self, command: str, new_state: str) -> None:
        # The keeper's own commands must not count as activity, or sitting
        # would forever reset the clock that leads to lying down.
        before = getattr(self.controller, "last_motion_at", None)
        ok = self.controller.send_command(command)
        if before is not None:
            self.controller.last_motion_at = before
        if ok:
            with self._lock:
                self.state = new_state
                self.transitions += 1
            logger.info("Idle keeper: %s (%s)", new_state, command)

    def _run(self) -> None:
        while not self._stop.wait(self.tick_s):
            if not self.enabled or self.suppressed():
                continue
            last = getattr(self.controller, "last_motion_at", None)
            if last is None:
                continue
            idle = time.time() - last
            with self._lock:
                state = self.state
            if idle < self.sit_after_s:
                if state != self.ACTIVE:
                    with self._lock:
                        self.state = self.ACTIVE
                continue
            if idle >= self.rest_after_s and state != self.LYING:
                self._settle("krest", self.LYING)
            elif idle < self.rest_after_s and state == self.ACTIVE:
                self._settle("ksit", self.SITTING)

    def status(self) -> dict:
        with self._lock:
            return {"enabled": self.enabled, "state": self.state,
                    "sitAfterS": self.sit_after_s,
                    "restAfterS": self.rest_after_s,
                    "transitions": self.transitions}
