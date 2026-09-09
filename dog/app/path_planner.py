"""A* over the occupancy grid, then the route as turn-and-advance legs.

Occupied cells and their one-cell halo (the dog is ~15 cm wide, cells are
10 cm) are impassable; unknown cells are allowed at a higher cost so a
route prefers floor she has seen but can still cross into the unexplored.
The cell path is pruned by line of sight into a few waypoints, and each
waypoint becomes a leg: turn to its bearing, then advance its distance.
The advance is converted with the calibrated stride model
(first cycle 0.10 m, then 0.112 m per cycle) into bounded `kwkF n` bursts.
"""
import heapq
import math

from app.occupancy import OccupancyGrid, UNKNOWN

DEFAULTS = {
    "inflateCells": 1,
    "unknownCost": 1.6,
    "marginCells": 12,
    "maxNodes": 60000,
    "goalSearchCells": 3,
    "strideFirstCycleM": 0.10,
    "strideMPerCycle": 0.112,
    "maxCyclesPerBurst": 3,
    "minTurnDeg": 12.0,
    "arriveWithinM": 0.15,
}

NEIGHBOURS = [(1, 0, 1.0), (-1, 0, 1.0), (0, 1, 1.0), (0, -1, 1.0),
              (1, 1, math.sqrt(2)), (1, -1, math.sqrt(2)),
              (-1, 1, math.sqrt(2)), (-1, -1, math.sqrt(2))]


def norm_deg(deg: float) -> float:
    return (deg + 180.0) % 360.0 - 180.0


class PathPlanner:
    def __init__(self, grid: OccupancyGrid, config: dict | None = None):
        self.grid = grid
        self.config = {**DEFAULTS, **(config or {})}

    # ---- search ------------------------------------------------------------

    def blocked_cells(self) -> set[tuple[int, int]]:
        occupied = self.grid.occupied_cells()
        r = int(self.config["inflateCells"])
        if r <= 0:
            return occupied
        halo = set()
        for cx, cy in occupied:
            for dx in range(-r, r + 1):
                for dy in range(-r, r + 1):
                    halo.add((cx + dx, cy + dy))
        return halo

    def plan(self, start_xy: tuple[float, float],
             goal_xy: tuple[float, float]) -> dict:
        start = self.grid.cell_of(*start_xy)
        goal = self.grid.cell_of(*goal_xy)
        blocked = self.blocked_cells()
        bounds = self._search_bounds(start, goal)
        if goal in blocked:
            nearest = self._nearest_open(goal, blocked)
            if nearest is None:
                return {"ok": False, "reason": "target is inside an obstacle",
                        "waypoints": []}
            goal = nearest
        blocked.discard(start)   # she is standing here, whatever the map says
        cells = self._astar(start, goal, blocked, bounds)
        if cells is None:
            return {"ok": False, "reason": "no route through the known map",
                    "waypoints": []}
        pruned = self._prune(cells, blocked)
        waypoints = [self.grid.center(*c) for c in pruned[1:]]
        if waypoints:
            waypoints[-1] = (float(goal_xy[0]), float(goal_xy[1])) \
                if goal == self.grid.cell_of(*goal_xy) else waypoints[-1]
        return {"ok": True, "waypoints": [(round(x, 3), round(y, 3)) for x, y in waypoints],
                "cells": len(cells), "explored": self._explored,
                "goalCell": list(goal)}

    def _search_bounds(self, start, goal) -> tuple[int, int, int, int]:
        m = int(self.config["marginCells"])
        known = self.grid.bounds()
        xs = [start[0], goal[0]] + ([known[0], known[1]] if known else [])
        ys = [start[1], goal[1]] + ([known[2], known[3]] if known else [])
        return (min(xs) - m, max(xs) + m, min(ys) - m, max(ys) + m)

    def _nearest_open(self, goal, blocked):
        radius = int(self.config["goalSearchCells"])
        best = None
        for dx in range(-radius, radius + 1):
            for dy in range(-radius, radius + 1):
                cell = (goal[0] + dx, goal[1] + dy)
                if cell in blocked:
                    continue
                d = dx * dx + dy * dy
                if best is None or d < best[0]:
                    best = (d, cell)
        return best[1] if best else None

    def _astar(self, start, goal, blocked, bounds):
        unknown_cost = float(self.config["unknownCost"])
        max_nodes = int(self.config["maxNodes"])

        def h(c):
            dx, dy = abs(c[0] - goal[0]), abs(c[1] - goal[1])
            return (dx + dy) + (math.sqrt(2) - 2) * min(dx, dy)

        open_heap = [(h(start), 0.0, start)]
        came: dict = {start: None}
        g: dict = {start: 0.0}
        closed: set = set()
        self._explored = 0
        while open_heap:
            _, cost, current = heapq.heappop(open_heap)
            if current in closed:
                continue
            closed.add(current)
            self._explored += 1
            if current == goal:
                path = []
                while current is not None:
                    path.append(current)
                    current = came[current]
                return path[::-1]
            if self._explored > max_nodes:
                return None
            for dx, dy, step in NEIGHBOURS:
                nxt = (current[0] + dx, current[1] + dy)
                if nxt in closed or nxt in blocked:
                    continue
                if not (bounds[0] <= nxt[0] <= bounds[1] and bounds[2] <= nxt[1] <= bounds[3]):
                    continue
                if dx and dy and ((current[0] + dx, current[1]) in blocked
                                  or (current[0], current[1] + dy) in blocked):
                    continue   # no cutting corners past an obstacle
                weight = unknown_cost if self.grid.state(*nxt) == UNKNOWN else 1.0
                tentative = cost + step * weight
                if tentative < g.get(nxt, math.inf):
                    g[nxt] = tentative
                    came[nxt] = current
                    heapq.heappush(open_heap, (tentative + h(nxt), tentative, nxt))
        return None

    # ---- simplification ----------------------------------------------------

    @staticmethod
    def _line_cells(a, b) -> list[tuple[int, int]]:
        """Cells the segment between two cell centres touches, sampled at a
        quarter cell so no crossed cell is skipped."""
        (x0, y0), (x1, y1) = a, b
        steps = max(1, int(4 * max(abs(x1 - x0), abs(y1 - y0))))
        out: list[tuple[int, int]] = []
        for i in range(steps + 1):
            t = i / steps
            cell = (math.floor(x0 + 0.5 + (x1 - x0) * t),
                    math.floor(y0 + 0.5 + (y1 - y0) * t))
            if not out or out[-1] != cell:
                out.append(cell)
        return out

    def _shortcut_ok(self, path_cells, blocked) -> bool:
        """A shortcut may not cross an obstacle, and may not touch more
        unknown cells than the searched sub-path it replaces, or the detour
        over seen floor that A* paid for would be pruned straight back
        through the unexplored."""
        line = self._line_cells(path_cells[0], path_cells[-1])
        if any(cell in blocked for cell in line):
            return False
        unknown_on_line = sum(1 for c in line if self.grid.state(*c) == UNKNOWN)
        unknown_on_path = sum(1 for c in path_cells if self.grid.state(*c) == UNKNOWN)
        return unknown_on_line <= unknown_on_path

    def _prune(self, cells, blocked):
        if len(cells) <= 2:
            return cells
        out = [cells[0]]
        anchor = 0
        i = 1
        while i < len(cells):
            if i == len(cells) - 1:
                out.append(cells[i])
                break
            if not self._shortcut_ok(cells[anchor:i + 2], blocked):
                out.append(cells[i])
                anchor = i
            i += 1
        return out

    # ---- legs --------------------------------------------------------------

    def cycles_for(self, distance_m: float) -> int:
        first = float(self.config["strideFirstCycleM"])
        per = float(self.config["strideMPerCycle"])
        if distance_m < first / 2:
            return 0
        return max(1, int(round((distance_m - first) / per)) + 1)

    def distance_for(self, cycles: int) -> float:
        if cycles <= 0:
            return 0.0
        return float(self.config["strideFirstCycleM"]) + \
            float(self.config["strideMPerCycle"]) * (cycles - 1)

    def leg(self, pose: dict, waypoint: tuple[float, float]) -> dict:
        dx = waypoint[0] - float(pose["x"])
        dy = waypoint[1] - float(pose["y"])
        distance = math.hypot(dx, dy)
        bearing = math.degrees(math.atan2(dy, dx)) if distance > 1e-6 else float(pose["heading"])
        turn = norm_deg(bearing - float(pose["heading"]))
        if abs(turn) < float(self.config["minTurnDeg"]):
            turn = 0.0
        return {"bearing": round(bearing, 1), "distanceM": round(distance, 3),
                "turnDeg": round(turn, 1),
                "cycles": self.cycles_for(distance),
                "arrived": distance <= float(self.config["arriveWithinM"])}

    def turn_command(self, turn_deg: float) -> str:
        deg = int(round(min(179, abs(turn_deg))))
        return f"kwk{'L' if turn_deg > 0 else 'R'} {deg}"

    def advance_commands(self, cycles: int) -> list[str]:
        burst = int(self.config["maxCyclesPerBurst"])
        out = []
        while cycles > 0:
            n = min(burst, cycles)
            out.append(f"kwkF {n}")
            cycles -= n
        return out
