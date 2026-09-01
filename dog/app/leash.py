"""Proximity leash: zone state machine over the firmware's event_rssi push.

Away mode: the dog's WiFi AP is the owner's phone hotspot, so the AP RSSI is
a direct dog<->owner distance signal. This service smooths it (median-of-5
then EMA), classifies it into zones with hysteresis + dwell, and forwards
zone transitions into the behavior framework as leash.* events — reactions
are ordinary data-driven bindings, not code.

Design: docs/design/PROXIMITY_LEASH_BRIEF.md (orchestrator repo).
- Zones: near / warn / far / lost (+ unknown before data arrives).
- "lost" also fires on report silence (frames stop = WiFi gone = leash
  broken); the firmware-side dead-man (XWd) is the safety floor beneath us.
- RSSI maps to zones, never to meters: thresholds come from walk-test marks.
"""
import logging
import statistics
import threading
import time

logger = logging.getLogger(__name__)

ZONES = ("near", "warn", "far", "lost")

DEFAULTS = {
    "warnDbm": -72.0,   # entering warn (worse than this)
    "farDbm": -80.0,    # entering far
    "lostDbm": -90.0,   # entering lost
    "hysteresisDb": 6.0,  # recovery requires this much improvement
    "dwellS": 2.5,        # zone must persist this long before switching
    "lostAfterS": 8.0,    # frame silence -> lost
    "deadManS": 20,       # firmware dead-man timeout armed with the leash
    "beaconIntervalS": 4.0,  # beacon mode: seconds between XWs scans
}

# Signal sources:
# - "ap": the firmware's event_rssi push — RSSI of the CONNECTED AP. Correct
#   for away mode, where the AP is the phone's hotspot.
# - "beacon": periodic XWs scans track a named SSID's beacon RSSI while the
#   dog stays on home WiFi — a phone-anchored leash indoors. Requires the
#   phone to keep beaconing (hotspot screen open, or any connected client).
STRING_CONFIG = ("mode", "beaconSsid")


class LeashService:
    """Consumes event_rssi frames; emits leash.* events while enabled."""

    def __init__(self, controller, event_binder, config: dict | None = None):
        self.controller = controller
        self.event_binder = event_binder
        self.config = {**DEFAULTS, "mode": "ap", "beaconSsid": "",
                       **(config or {})}
        self.enabled = False

        self._lock = threading.Lock()
        self._raw: list[float] = []       # last 5 raw samples (median window)
        self._smoothed: float | None = None
        self._zone = "unknown"
        self._candidate: str | None = None
        self._candidate_since = 0.0
        self._last_frame_at = 0.0
        self._last_raw: float | None = None
        self._ssid: str | None = None
        self._marks: list[dict] = []      # walk-test captures
        self._stop = threading.Event()
        self._watchdog = threading.Thread(target=self._silence_loop,
                                          daemon=True)
        self._watchdog.start()
        threading.Thread(target=self._beacon_loop, daemon=True).start()

    # ---- input -------------------------------------------------------------

    def handle_event_frame(self, frame: dict) -> None:
        if frame.get("type") != "event_rssi":
            return
        if self.config.get("mode") == "beacon":
            return  # AP RSSI is dog<->router here — the wrong signal
        rssi = frame.get("rssi")
        if not isinstance(rssi, (int, float)):
            return
        self._ingest(float(rssi), frame.get("ssid"))

    def _ingest(self, rssi: float, ssid: str | None) -> None:
        now = time.time()
        with self._lock:
            self._last_frame_at = now
            self._last_raw = rssi
            self._ssid = ssid
            self._raw.append(rssi)
            if len(self._raw) > 5:
                self._raw.pop(0)
            median = statistics.median(self._raw)
            self._smoothed = (median if self._smoothed is None
                              else 0.7 * self._smoothed + 0.3 * median)
            self._classify(self._smoothed, now)

    def _beacon_loop(self) -> None:
        """Beacon mode: track a named SSID's advertisement RSSI via XWs
        scans. Each scan blocks the firmware ~2 s; missed beacons simply
        don't update _last_frame_at, so the silence watchdog handles lost."""
        while not self._stop.wait(max(1.0, float(self.config["beaconIntervalS"]))):
            if not self.enabled or self.config.get("mode") != "beacon":
                continue
            target = self.config.get("beaconSsid") or ""
            if not target:
                continue
            try:
                lines = self.controller.query("XWs")
            except Exception:
                logger.exception("Beacon scan failed")
                continue
            if not lines:
                continue
            import json as _json
            for raw in "\n".join(lines).splitlines():
                raw = raw.strip()
                if not raw.startswith("{"):
                    continue
                try:
                    ap = _json.loads(raw)
                except _json.JSONDecodeError:
                    continue
                if ap.get("ssid") == target and \
                        isinstance(ap.get("rssi"), (int, float)):
                    self._ingest(float(ap["rssi"]), target)
                    break

    # ---- zone machine ------------------------------------------------------

    def _zone_for(self, dbm: float) -> str:
        """Worsening enters a zone at its plain threshold; recovering to a
        better zone must clear the threshold by hysteresisDb."""
        order = ["near", "warn", "far", "lost"]
        cfg = self.config
        thresholds = (cfg["warnDbm"], cfg["farDbm"], cfg["lostDbm"])
        current = order.index(self._zone) if self._zone in order else 0

        entry = sum(1 for t in thresholds if dbm <= t)
        recovery = sum(1 for t in thresholds
                       if dbm <= t + cfg["hysteresisDb"])
        if entry > current:
            return order[entry]
        if recovery < current:
            return order[recovery]
        return order[current]

    def _classify(self, dbm: float, now: float) -> None:
        """Called under lock. Dwell-gated zone switching."""
        target = self._zone_for(dbm)
        if target == self._zone:
            self._candidate = None
            return
        if target != self._candidate:
            self._candidate = target
            self._candidate_since = now
            return
        if now - self._candidate_since >= self.config["dwellS"]:
            self._transition(target, dbm)

    def _transition(self, zone: str, dbm: float | None) -> None:
        """Called under lock."""
        previous, self._zone = self._zone, zone
        self._candidate = None
        logger.info("Leash zone: %s -> %s (%.1f dBm)", previous, zone,
                    dbm if dbm is not None else float("nan"))
        if self.enabled:
            payload = {"zone": zone, "previous": previous,
                       "rssi": round(dbm, 1) if dbm is not None else None}
            # Off-thread: trigger() submits to the arbiter which takes locks.
            threading.Thread(target=self.event_binder.trigger,
                             args=(f"leash.{zone}", payload),
                             daemon=True).start()

    def _silence_loop(self) -> None:
        while not self._stop.wait(1.0):
            with self._lock:
                if not self.enabled or self._zone == "lost":
                    continue
                if self._last_frame_at and \
                        time.time() - self._last_frame_at > self.config["lostAfterS"]:
                    # Frame silence: WiFi (and with it the leash) is gone.
                    self._transition("lost", self._smoothed)

    # ---- control -----------------------------------------------------------

    def set_enabled(self, enabled: bool) -> dict:
        self.enabled = bool(enabled)
        # Arm/disarm the firmware dead-man alongside the host-side leash:
        # it is the safety floor for the one failure the host cannot handle
        # (link fully gone). Best-effort — mock mode has no XW tokens.
        try:
            if self.enabled:
                self.controller.send_command(
                    f"XWd1 {int(self.config['deadManS'])}")
            else:
                self.controller.send_command("XWd0")
        except Exception:
            logger.warning("Dead-man toggle failed", exc_info=True)
        with self._lock:
            self._zone = "unknown"
            self._candidate = None
            if self.enabled:
                # Arming grace: restart the silence clock and drop stale
                # samples so enabling never instantly fires "lost" off data
                # from before the leash was on (observed live 2026-09-01).
                self._last_frame_at = time.time()
                self._raw.clear()
                self._smoothed = None
        return self.status()

    def configure(self, updates: dict) -> dict:
        numeric = {k: float(v) for k, v in updates.items()
                   if k in DEFAULTS and isinstance(v, (int, float))}
        strings = {k: str(v) for k, v in updates.items()
                   if k in STRING_CONFIG and isinstance(v, str)}
        self.config.update(numeric)
        self.config.update(strings)
        if self.config.get("mode") == "beacon":
            # Beacons arrive per scan interval, not at 1 Hz — the silence
            # watchdog must tolerate a couple of missed scans.
            floor = 3.0 * float(self.config["beaconIntervalS"])
            if self.config["lostAfterS"] < floor:
                self.config["lostAfterS"] = floor
        if numeric or strings:
            with self._lock:
                self._raw.clear()
                self._smoothed = None  # re-converge on the new signal source
        return self.status()

    def mark(self, label: str) -> dict:
        """Walk-test capture: record the current smoothed RSSI under a label."""
        with self._lock:
            entry = {"label": label, "rssi": self._smoothed,
                     "at": time.time()}
            self._marks.append(entry)
            self._marks = self._marks[-20:]
        return entry

    def status(self) -> dict:
        with self._lock:
            age = (time.time() - self._last_frame_at
                   if self._last_frame_at else None)
            return {
                "enabled": self.enabled,
                "zone": self._zone if self.enabled else "disabled",
                "rssi": round(self._smoothed, 1)
                        if self._smoothed is not None else None,
                "rssiRaw": self._last_raw,
                "ssid": self._ssid,
                "frameAgeS": round(age, 1) if age is not None else None,
                "config": dict(self.config),
                "marks": list(self._marks),
            }

    def shutdown(self) -> None:
        self._stop.set()
