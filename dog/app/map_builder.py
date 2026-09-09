"""Sensor -> grid: turns one ultrasonic reading into cell observations.

A reading is a ray from the dog's position along its heading (plus the head
pan when the ranger rides the head). Cells the ray crosses before the echo
are observed free; the cell at the echo distance is observed occupied. No
echo means "nothing within the firmware's 2 m window", which the validation
notes trace to the target rather than the sensor, so it is not trusted as
free space. Readings shorter than the dog's own snout are dropped: the beam
sometimes catches a leg.

Before writing, the builder compares the reading with what the grid already
believes and reports contradictions (a confident free cell echoing, a
confident wall the beam passed through). Deciding whether that is noise or
news is the navigator's job through the error handler; the builder only
reports and then integrates the reading as usual.
"""
import math
import threading
import time

from app.occupancy import FREE, OCCUPIED, OccupancyGrid

CONFIDENT_FREE = -1.2       # three net misses
CONFIDENT_OCCUPIED = 1.7    # two hits and no misses

DEFAULTS = {
    "maxRangeM": 2.0,
    "minRangeCm": 4.0,
    "sensorOffsetM": 0.0,     # ranger ahead of the pose origin along the heading
    "flushS": 5.0,
}


class MapBuilder:
    def __init__(self, grid: OccupancyGrid, config: dict | None = None,
                 clock=time.time):
        self.grid = grid
        self.config = {**DEFAULTS, **(config or {})}
        self._clock = clock
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self.stats = {"integrated": 0, "skipped": 0, "contradictions": 0,
                      "lastIntegratedAt": None}

    # ---- lifecycle ---------------------------------------------------------

    def start_flusher(self) -> None:
        threading.Thread(target=self._flush_loop, daemon=True).start()

    def stop(self) -> None:
        self._stop.set()
        self.grid.save()

    def _flush_loop(self) -> None:
        while not self._stop.wait(float(self.config["flushS"])):
            try:
                self.grid.save()
            except Exception:
                pass

    # ---- ray casting -------------------------------------------------------

    def ray_cells(self, x: float, y: float, bearing_deg: float,
                  length_m: float) -> list[tuple[int, int]]:
        """Cells crossed from (x, y) along the bearing, in order, deduplicated,
        sampled at half a cell so no cell on the ray is skipped."""
        res = self.grid.resolution
        step = res / 2.0
        rad = math.radians(bearing_deg)
        dx, dy = math.cos(rad), math.sin(rad)
        cells: list[tuple[int, int]] = []
        seen: set[tuple[int, int]] = set()
        n = int(length_m / step) + 1
        for i in range(n + 1):
            d = min(i * step, length_m)
            cell = self.grid.cell_of(x + dx * d, y + dy * d)
            if cell not in seen:
                seen.add(cell)
                cells.append(cell)
        return cells

    def integrate(self, distance_cm: float | None, pose: dict,
                  pan_deg: float = 0.0) -> dict:
        """One reading at `pose` ({x, y, heading}) with the ranger panned
        `pan_deg` left of the heading. Returns what was written plus any
        contradictions found before writing."""
        bearing = float(pose["heading"]) + float(pan_deg)
        rad = math.radians(bearing)
        offset = float(self.config["sensorOffsetM"])
        x = float(pose["x"]) + math.cos(rad) * offset
        y = float(pose["y"]) + math.sin(rad) * offset
        result = {"bearing": round(bearing, 1), "freed": 0, "hit": None,
                  "contradictions": [], "skipped": None}
        if distance_cm is None:
            result["skipped"] = "no echo"
            self.stats["skipped"] += 1
            return result
        if distance_cm < float(self.config["minRangeCm"]):
            result["skipped"] = "too close (own body?)"
            self.stats["skipped"] += 1
            return result
        max_range = float(self.config["maxRangeM"])
        distance_m = distance_cm / 100.0
        echo = distance_m < max_range
        length = min(distance_m, max_range)
        cells = self.ray_cells(x, y, bearing, length)
        if not cells:
            result["skipped"] = "empty ray"
            return result
        end = cells[-1] if echo else None
        free_cells = cells[:-1] if echo else cells
        origin_cell = self.grid.cell_of(float(pose["x"]), float(pose["y"]))
        with self._lock:
            for cell in free_cells:
                if cell == end:
                    continue
                if self.grid.logodds(*cell) >= CONFIDENT_OCCUPIED and cell != origin_cell:
                    result["contradictions"].append({
                        "kind": "free_where_occupied", "cx": cell[0], "cy": cell[1],
                        "logodds": round(self.grid.logodds(*cell), 2)})
            if end is not None and self.grid.logodds(*end) <= CONFIDENT_FREE:
                result["contradictions"].append({
                    "kind": "occupied_where_free", "cx": end[0], "cy": end[1],
                    "logodds": round(self.grid.logodds(*end), 2)})
            for cell in free_cells:
                if cell != end:
                    self.grid.observe_free(*cell)
                    result["freed"] += 1
            if end is not None:
                state = self.grid.observe_hit(*end)
                result["hit"] = {"cx": end[0], "cy": end[1], "state": state,
                                 "x": round(x + math.cos(rad) * distance_m, 2),
                                 "y": round(y + math.sin(rad) * distance_m, 2)}
        self.stats["integrated"] += 1
        self.stats["contradictions"] += len(result["contradictions"])
        self.stats["lastIntegratedAt"] = self._clock()
        return result

    def integrate_sweep(self, readings: list[tuple[float, float | None]],
                        pose: dict) -> dict:
        """Head-pan sweep: [(pan_deg, distance_cm), ...] from one standing pose."""
        results = [self.integrate(distance, pose, pan) for pan, distance in readings]
        return {"readings": len(readings),
                "hits": sum(1 for r in results if r["hit"]),
                "freed": sum(r["freed"] for r in results),
                "contradictions": [c for r in results for c in r["contradictions"]]}

    def apply_correction(self, cells: list[dict], trust: str) -> int:
        """Human verdict on a contradiction: 'sensor' pins the reading's
        version of the cells, 'map' pins what the map believed."""
        changed = 0
        for item in cells:
            cx, cy, kind = int(item["cx"]), int(item["cy"]), item["kind"]
            sensor_says = OCCUPIED if kind == "occupied_where_free" else FREE
            map_says = FREE if kind == "occupied_where_free" else OCCUPIED
            self.grid.set_state(cx, cy, sensor_says if trust == "sensor" else map_says)
            changed += 1
        return changed

    def status(self) -> dict:
        return {"config": dict(self.config), **self.stats,
                "grid": {"resolutionM": self.grid.resolution,
                         "version": self.grid.version, **self.grid.counts()}}
