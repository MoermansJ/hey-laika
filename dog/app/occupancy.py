"""Occupancy grid: the floor as Laika has sensed it, 10 cm cells.

World frame is the senses layer's: x east, y north in metres, heading in
degrees counter-clockwise from +x, origin wherever the pose was last reset.
A cell is addressed by integer indices (floor(x / res), floor(y / res)).

Each cell carries a log-odds occupancy value updated by ray casts (a miss
pushes it toward free, a hit toward occupied) so one noisy echo never paints
a wall: a cell reads "occupied" only after two net hits. Cells the human
corrects from the GUI are pinned near the clamp so a single later reading
cannot flip them back. The grid persists in the adapter's SQLite database
(table map_cells); dirty cells are written by save(), called by the map
builder's flush timer and on shutdown.
"""
import math
import threading
import time

from sqlalchemy import Float, Integer
from sqlalchemy.orm import Mapped, mapped_column

from app.models import Base, SessionLocal, engine

HIT_STEP = 0.85
MISS_STEP = -0.4
CLAMP = 4.0
OCCUPIED_AT = 1.5          # two net hits
FREE_AT = -0.4             # one net miss
PINNED = 3.0               # human-corrected cells

FREE, OCCUPIED, UNKNOWN = "free", "occupied", "unknown"


class MapCell(Base):
    __tablename__ = "map_cells"

    cx: Mapped[int] = mapped_column(Integer, primary_key=True)
    cy: Mapped[int] = mapped_column(Integer, primary_key=True)
    logodds: Mapped[float] = mapped_column(Float, default=0.0)
    hits: Mapped[int] = mapped_column(Integer, default=0)
    misses: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[float] = mapped_column(Float, default=0.0)


def state_of(logodds: float) -> str:
    if logodds >= OCCUPIED_AT:
        return OCCUPIED
    if logodds <= FREE_AT:
        return FREE
    return UNKNOWN


class OccupancyGrid:
    def __init__(self, resolution_m: float = 0.10, clock=time.time):
        self.resolution = float(resolution_m)
        self._clock = clock
        self._lock = threading.RLock()
        self._cells: dict[tuple[int, int], list] = {}   # (cx, cy) -> [logodds, hits, misses, updated]
        self._dirty: set[tuple[int, int]] = set()
        self._cleared = False
        self.version = 0

    # ---- geometry ----------------------------------------------------------

    def cell_of(self, x: float, y: float) -> tuple[int, int]:
        # The epsilon keeps 0.6 / 0.1 (= 5.999...) in cell 6, not 5.
        return (math.floor(x / self.resolution + 1e-9),
                math.floor(y / self.resolution + 1e-9))

    def center(self, cx: int, cy: int) -> tuple[float, float]:
        return ((cx + 0.5) * self.resolution, (cy + 0.5) * self.resolution)

    # ---- observations ------------------------------------------------------

    def _bump(self, cx: int, cy: int, step: float, hit: bool) -> str:
        with self._lock:
            cell = self._cells.get((cx, cy))
            if cell is None:
                cell = [0.0, 0, 0, 0.0]
                self._cells[(cx, cy)] = cell
            cell[0] = max(-CLAMP, min(CLAMP, cell[0] + step))
            if hit:
                cell[1] += 1
            else:
                cell[2] += 1
            cell[3] = self._clock()
            self._dirty.add((cx, cy))
            self.version += 1
            return state_of(cell[0])

    def observe_hit(self, cx: int, cy: int) -> str:
        return self._bump(cx, cy, HIT_STEP, True)

    def observe_free(self, cx: int, cy: int) -> str:
        return self._bump(cx, cy, MISS_STEP, False)

    def set_state(self, cx: int, cy: int, state: str) -> dict:
        """Human correction: pin a cell as free or occupied, or forget it."""
        with self._lock:
            if state == UNKNOWN:
                self._cells.pop((cx, cy), None)
                self._dirty.add((cx, cy))
                self.version += 1
                return self.get_cell(cx, cy)
            cell = self._cells.setdefault((cx, cy), [0.0, 0, 0, 0.0])
            cell[0] = PINNED if state == OCCUPIED else -PINNED
            cell[3] = self._clock()
            self._dirty.add((cx, cy))
            self.version += 1
            return self.get_cell(cx, cy)

    # ---- queries -----------------------------------------------------------

    def logodds(self, cx: int, cy: int) -> float:
        with self._lock:
            cell = self._cells.get((cx, cy))
            return cell[0] if cell else 0.0

    def state(self, cx: int, cy: int) -> str:
        return state_of(self.logodds(cx, cy))

    def is_blocked(self, cx: int, cy: int) -> bool:
        return self.logodds(cx, cy) >= OCCUPIED_AT

    def get_cell(self, cx: int, cy: int) -> dict:
        with self._lock:
            cell = self._cells.get((cx, cy)) or [0.0, 0, 0, 0.0]
        return {"cx": cx, "cy": cy, "state": state_of(cell[0]),
                "logodds": round(cell[0], 2), "hits": cell[1],
                "misses": cell[2], "updatedAt": cell[3] or None}

    def cells(self, bounds: tuple[int, int, int, int] | None = None,
              known_only: bool = True) -> list[dict]:
        """Cells as dicts; bounds = (minCx, maxCx, minCy, maxCy) inclusive."""
        with self._lock:
            items = list(self._cells.items())
        out = []
        for (cx, cy), cell in items:
            if bounds and not (bounds[0] <= cx <= bounds[1]
                               and bounds[2] <= cy <= bounds[3]):
                continue
            state = state_of(cell[0])
            if known_only and state == UNKNOWN:
                continue
            out.append({"cx": cx, "cy": cy, "state": state,
                        "logodds": round(cell[0], 2)})
        return out

    def bounds(self) -> tuple[int, int, int, int] | None:
        with self._lock:
            if not self._cells:
                return None
            xs = [c[0] for c in self._cells]
            ys = [c[1] for c in self._cells]
        return (min(xs), max(xs), min(ys), max(ys))

    def occupied_cells(self) -> set[tuple[int, int]]:
        with self._lock:
            return {key for key, cell in self._cells.items()
                    if cell[0] >= OCCUPIED_AT}

    def counts(self) -> dict:
        with self._lock:
            values = [cell[0] for cell in self._cells.values()]
        return {"known": sum(1 for v in values if state_of(v) != UNKNOWN),
                "free": sum(1 for v in values if state_of(v) == FREE),
                "occupied": sum(1 for v in values if state_of(v) == OCCUPIED),
                "touched": len(values)}

    def to_json(self) -> dict:
        bounds = self.bounds()
        return {"resolutionM": self.resolution, "version": self.version,
                "bounds": None if bounds is None else
                {"minCx": bounds[0], "maxCx": bounds[1],
                 "minCy": bounds[2], "maxCy": bounds[3]},
                "counts": self.counts(),
                "cells": [[c["cx"], c["cy"], c["state"][0], c["logodds"]]
                          for c in self.cells()]}

    def clear(self) -> None:
        with self._lock:
            keys = list(self._cells)
            self._cells.clear()
            self._dirty.update(keys)
            self._cleared = True
            self.version += 1

    # ---- persistence -------------------------------------------------------

    def load(self) -> int:
        Base.metadata.create_all(engine, tables=[MapCell.__table__])
        with SessionLocal() as session:
            rows = session.query(MapCell).all()
        with self._lock:
            self._cells = {(r.cx, r.cy): [r.logodds, r.hits, r.misses, r.updated_at]
                           for r in rows}
            self._dirty.clear()
            self.version += 1
        return len(rows)

    def save(self) -> int:
        with self._lock:
            dirty = list(self._dirty)
            self._dirty.clear()
            cleared = self._cleared
            self._cleared = False
            snapshot = {key: list(self._cells[key]) for key in dirty
                        if key in self._cells}
        if not dirty and not cleared:
            return 0
        with SessionLocal() as session:
            if cleared:
                session.query(MapCell).delete()
            for key in dirty:
                cell = snapshot.get(key)
                if cell is None:
                    session.query(MapCell).filter_by(cx=key[0], cy=key[1]).delete()
                    continue
                session.merge(MapCell(cx=key[0], cy=key[1], logodds=cell[0],
                                      hits=cell[1], misses=cell[2],
                                      updated_at=cell[3]))
            session.commit()
        return len(dirty)
