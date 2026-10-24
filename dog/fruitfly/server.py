"""Fruitfly F2 bridge, live side (PERSONALITY_MODES_BRIEF.md §6.1/§6.3): the
same leaky-rate connectome model as sim.py's bench spike (reusing sim.tick so
the two never drift apart), run with no fixed end time and serving the
current decoded command over plain HTTP on localhost so
dog/app/fruitfly_drive.py can poll it ("the same trust boundary as Ollama
today" per §6.1). Headless and arbiter-free here — the adapter owns that
bridge; this process only ever answers GET /command.
"""
import argparse
import json
import logging
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import numpy as np

import build_matrix
import sim

logger = logging.getLogger(__name__)


class _SharedState:
    def __init__(self):
        self._lock = threading.Lock()
        self._snapshot = {"state": "STOP", "signals": {}, "tick": 0, "t": 0.0}

    def update(self, state: str, signals: dict, tick: int, t: float) -> None:
        with self._lock:
            self._snapshot = {"state": state, "signals": signals, "tick": tick,
                              "t": round(t, 3)}

    def snapshot(self) -> dict:
        with self._lock:
            return dict(self._snapshot)


def _make_handler(shared: _SharedState):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args) -> None:
            pass  # the tick loop's own print/logger covers state transitions

        def do_GET(self) -> None:
            if self.path != "/command":
                self.send_response(404)
                self.end_headers()
                return
            body = json.dumps(shared.snapshot()).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
    return Handler


def serve(host: str, port: int, hz: float, gain: float, bias: float, tau: float,
          drive_mean: float, drive_noise: float, seed: int, quiet: bool) -> None:
    print("Loading connectome matrix ...")
    matrix, index = build_matrix.load()
    n = matrix.shape[0]
    readout = sim.build_readout(index)
    drive_idx = np.where(sim.sensory_mask(index))[0]
    print(f"Readout populations: forward={len(readout.forward_idx)} "
          f"backward={len(readout.backward_idx)} "
          f"turn_left={len(readout.turn_left_idx)} turn_right={len(readout.turn_right_idx)}")

    shared = _SharedState()
    httpd = ThreadingHTTPServer((host, port), _make_handler(shared))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    logger.info("Fruitfly sim serving http://%s:%d/command", host, port)
    print(f"Serving http://{host}:{port}/command (Ctrl+C to stop)")

    rng = np.random.default_rng(seed)
    activity = np.zeros(n, dtype=np.float32)
    dt = 1.0 / hz
    alpha = min(1.0, dt / tau)
    prev_state = readout.state
    tick_count = 0
    start = time.time()
    try:
        while True:
            loop_start = time.time()
            activity, state, signals = sim.tick(matrix, activity, readout, drive_idx, n,
                                                 gain, bias, alpha, drive_mean, drive_noise, rng)
            t = tick_count * dt
            shared.update(state, signals, tick_count, t)
            if not quiet and (tick_count == 0 or state != prev_state):
                print(f"t={t:8.2f}s  state={state:8s}  "
                      f"fwd={signals['forward']:.3f} bwd={signals['backward']:.3f} "
                      f"turn={signals['turn']:+.3f}")
            prev_state = state
            tick_count += 1
            remaining = dt - (time.time() - loop_start)
            if remaining > 0:
                time.sleep(remaining)
    except KeyboardInterrupt:
        pass
    finally:
        httpd.shutdown()
        elapsed = time.time() - start
        print(f"Stopped after {tick_count} ticks in {elapsed:.1f}s "
              f"({tick_count / max(elapsed, 1e-9):.1f} Hz actual)")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                      formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--host", default="127.0.0.1", help="loopback only by default")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--hz", type=float, default=10.0, help="tick rate (bench: ~34 Hz max on this CPU)")
    parser.add_argument("--gain", type=float, default=0.05)
    parser.add_argument("--bias", type=float, default=2.0)
    parser.add_argument("--tau", type=float, default=0.05)
    parser.add_argument("--drive-mean", type=float, default=4.0)
    parser.add_argument("--drive-noise", type=float, default=1.0)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    serve(args.host, args.port, args.hz, args.gain, args.bias, args.tau,
          args.drive_mean, args.drive_noise, args.seed, args.quiet)


if __name__ == "__main__":
    main()
