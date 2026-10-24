"""The phase 1 gate: every step of the reconstruction path, run for real.

    dog/reconstruction/.venv/Scripts/python dog/reconstruction/validate.py
    ... --offline      # everything that does not need Laika switched on

The rule from the design doc is that an unvalidated step fails the whole
run, so there is no "skipped" outcome here. The default run includes the
live-frame step and goes red until the stack is up; `--offline` drops the
steps that need hardware and says so in the summary, loudly, every time.

Each step prints PASS or FAIL with the numbers it checked, so a red run
says what broke rather than that something did. Kept out of dog/tests on
purpose: the adapter's pytest suite must not depend on this venv, the
weights, or a GPU.
"""
import argparse
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE.parent) not in sys.path:
    sys.path.insert(0, str(HERE.parent))

import numpy as np  # noqa: E402

from reconstruction import cloud, depth, fixtures, frames, settings as settings_module  # noqa: E402

OUT_DIR = HERE / "out"


class Gate:
    """Runs steps, remembers what happened, and decides the exit code."""

    def __init__(self):
        self.results = []

    def step(self, name: str, run) -> object:
        started = time.time()
        try:
            detail = run()
            ok = True
        except Exception as error:                   # noqa: BLE001 - the gate reports
            detail = f"{type(error).__name__}: {error}"
            ok = False
        elapsed = (time.time() - started) * 1000.0
        self.results.append((ok, name, detail, elapsed))
        print(f"{'PASS' if ok else 'FAIL'}  {name}  ({elapsed:.0f} ms)\n"
              f"      {detail}")
        return detail if ok else None

    def summary(self, excluded: list[str]) -> int:
        failed = [name for ok, name, _, _ in self.results if not ok]
        print("\n" + "-" * 68)
        print(f"{len(self.results) - len(failed)}/{len(self.results)} steps passed")
        for name in failed:
            print(f"  FAILED: {name}")
        for name in excluded:
            print(f"  EXCLUDED by --offline (not validated here): {name}")
        if failed:
            return 1
        if excluded:
            print("\nOFFLINE GATE GREEN. The full gate stays unproven until the "
                  "excluded steps run against the dog.")
        else:
            print("\nFULL GATE GREEN.")
        return 0


class _StubHandler(BaseHTTPRequestHandler):
    """Stands in for the adapter's /eyes/snap so the capture path is
    exercised with the dog switched off."""

    jpeg = b""
    seen = []

    def do_GET(self):                                # noqa: N802 - stdlib name
        _StubHandler.seen.append(self.path)
        if not self.path.startswith("/api/robots/") or "/eyes/snap" not in self.path:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", "image/jpeg")
        self.send_header("Content-Length", str(len(self.jpeg)))
        self.end_headers()
        self.wfile.write(self.jpeg)

    def log_message(self, *args):                    # keep the gate's output clean
        return


def _serve_stub(jpeg: bytes) -> tuple[ThreadingHTTPServer, str]:
    _StubHandler.jpeg = jpeg
    _StubHandler.seen = []
    server = ThreadingHTTPServer(("127.0.0.1", 0), _StubHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://127.0.0.1:{server.server_address[1]}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--offline", action="store_true",
                        help="drop the steps that need Laika powered on")
    parser.add_argument("--base-url", default="http://localhost:8080",
                        help="orchestrator (or adapter) for the live step")
    parser.add_argument("--robot-id", default=frames.DEFAULTS["robotId"])
    parser.add_argument("--model", default="small")
    args = parser.parse_args()

    gate = Gate()
    state = {}

    def environment():
        import onnxruntime as ort

        state["providers"] = ort.get_available_providers()
        assert "CPUExecutionProvider" in state["providers"], "no CPU provider"
        return (f"onnxruntime {ort.__version__}, providers "
                f"{state['providers']}, numpy {np.__version__}")

    def weights_present():
        model = depth.build_model(args.model)
        assert model.available, f"{model.model_path} missing; run " \
                                f"dog/tools/download_depth_model.py"
        state["model"] = model
        size_mb = model.model_path.stat().st_size / 1e6
        return f"{model.model_name} ({size_mb:.0f} MB)"

    def preprocessing():
        # QVGA through the model's own resize rule: both sides a multiple of
        # 14, aspect ratio kept, the easier side landing on 518.
        width, height = depth.resize_for_dpt(320, 240)
        assert width % 14 == 0 and height % 14 == 0, (width, height)
        assert 518 in (width, height), (width, height)
        assert abs((width / height) - (320 / 240)) < 0.05, (width, height)
        return f"320x240 -> {width}x{height}"

    def inference_on_photograph():
        model = state["model"]
        disparity, rgb = model.infer(fixtures.person_frame())
        assert disparity.shape == rgb.shape[:2], (disparity.shape, rgb.shape)
        assert np.isfinite(disparity).all(), "non-finite disparity"
        assert disparity.std() > 1e-3, "flat depth map"
        # A real photograph: the pavement at the bottom is nearer than the
        # top of the frame. Disparity is larger when nearer.
        rows = disparity.shape[0] // 3
        bottom, top = disparity[-rows:].mean(), disparity[:rows].mean()
        assert bottom > top, f"bottom {bottom:.2f} not nearer than top {top:.2f}"
        state["disparity"], state["rgb"] = disparity, rgb
        return (f"{model.provider}, {model.stats['inferenceMs']} ms, "
                f"bottom/top disparity {bottom:.1f}/{top:.1f}")

    def cpu_fallback():
        model = depth.build_model(args.model, providers=["CPUExecutionProvider"])
        disparity, _ = model.infer(fixtures.person_frame())
        assert model.provider == "CPUExecutionProvider", model.provider
        assert np.isfinite(disparity).all()
        return f"CPU path works, {model.stats['inferenceMs']} ms"

    def room_geometry():
        # Known geometry: the back wall is the far thing, the floor at the
        # bottom edge is the near thing.
        disparity, _ = state["model"].infer(fixtures.synthetic_room())
        height, width = disparity.shape
        wall = disparity[int(height * 0.35):int(height * 0.60),
                         int(width * 0.40):int(width * 0.60)].mean()
        floor = disparity[int(height * 0.90):, :].mean()
        assert floor > wall, f"floor {floor:.2f} not nearer than wall {wall:.2f}"
        return f"synthetic room: floor/wall disparity {floor:.1f}/{wall:.1f}"

    def cloud_geometry():
        resolved, _ = settings_module.resolve({"pointDensity": 5000})
        xyz, colours, stats = cloud.to_points(state["disparity"], state["rgb"],
                                              resolved)
        assert stats["points"] == 5000, stats["points"]
        assert xyz.shape == (5000, 3) and colours.shape == (5000, 3)
        assert np.isfinite(xyz).all(), "non-finite point"
        assert xyz[:, 2].min() >= resolved["nearM"] - 1e-3, xyz[:, 2].min()
        assert xyz[:, 2].max() <= resolved["farM"] + 1e-3, xyz[:, 2].max()
        again, _, _ = cloud.to_points(state["disparity"], state["rgb"], resolved)
        assert np.array_equal(xyz, again), "thinning is not deterministic"
        state["xyz"], state["colours"] = xyz, colours
        return (f"{stats['points']} points, depth "
                f"{stats['depthM']['min']}..{stats['depthM']['max']} m, "
                f"{stats['rejectedPct']}% rejected, deterministic")

    def density_setting():
        counts = []
        for budget in (1000, 20000):
            resolved, _ = settings_module.resolve({"pointDensity": budget})
            _, _, stats = cloud.to_points(state["disparity"], state["rgb"],
                                          resolved)
            counts.append(stats["points"])
        assert counts == [1000, 20000], counts
        return f"point counts track the budget: {counts}"

    def settings_clamps():
        resolved, notes = settings_module.resolve(
            {"pointDensity": 10 ** 9, "nearM": 3.0, "farM": 1.0,
             "model": "nope", "bogus": 1})
        assert resolved["pointDensity"] == settings_module.LIMITS["pointDensity"][1]
        assert resolved["farM"] > resolved["nearM"], resolved
        assert resolved["model"] == settings_module.DEFAULTS["model"]
        assert len(notes) >= 4, notes
        return f"{len(notes)} bad values clamped or refused, none raised"

    def ply_written():
        out = cloud.write_ply(OUT_DIR / "gate.ply", state["xyz"], state["colours"])
        body = out.read_bytes()
        header_end = body.index(b"end_header\n") + len(b"end_header\n")
        assert body.startswith(b"ply\n"), "not a PLY"
        assert f"element vertex {state['xyz'].shape[0]}".encode() in body
        assert len(body) - header_end == state["xyz"].shape[0] * 15, "short body"
        return f"{out.name}, {len(body) / 1e6:.2f} MB, header + 15 B per point"

    def wire_frame_format():
        blob = cloud.to_binary_frame(state["xyz"], state["colours"])
        count = int.from_bytes(blob[4:8], "little")
        assert blob[:4] == b"FLYC", blob[:4]
        assert count == state["xyz"].shape[0], count
        assert len(blob) == 16 + count * 15, len(blob)
        first = np.frombuffer(blob[16:28], dtype="<f4")
        assert np.allclose(first, state["xyz"][0]), (first, state["xyz"][0])
        return f"{count} points in {len(blob) / 1e6:.2f} MB binary"

    def preview_image():
        out = cloud.write_preview(OUT_DIR / "gate.preview.png", state["rgb"],
                                  state["disparity"])
        from PIL import Image

        with Image.open(out) as image:
            assert image.size == (state["rgb"].shape[1] * 2,
                                  state["rgb"].shape[0]), image.size
        return f"{out.name}, frame beside depth map"

    def capture_path_stubbed():
        server, base = _serve_stub(fixtures.person_frame())
        try:
            source = frames.FrameSource({"baseUrl": base, "robotId": "bittle-1"})
            body = source.fetch(fresh=True)
            assert body.startswith(b"\xff\xd8"), "not a JPEG"
            assert _StubHandler.seen[-1].endswith("?fresh=1"), _StubHandler.seen
            assert "/api/robots/bittle-1/eyes/snap" in _StubHandler.seen[-1]
            bad = frames.FrameSource({"baseUrl": base + "/nope"})
            try:
                bad.fetch()
                raise AssertionError("a 404 should raise FrameError")
            except frames.FrameError:
                pass
        finally:
            server.shutdown()
        return (f"{len(body)} B through {source.snap_url}?fresh=1, "
                f"404 raises FrameError")

    def service_endpoints():
        from reconstruction.server import create_app
        from reconstruction.service import Service

        service = Service({"pointDensity": 3000}, source="fixture")
        client = create_app(service).test_client()

        empty = client.get("/cloud")
        assert empty.status_code == 404, empty.status_code
        assert client.get("/cloud/stats").status_code == 404

        health = client.get("/health").get_json()
        assert health["ok"] and health["service"] == "reconstruction", health
        assert health["provider"].endswith("ExecutionProvider"), health
        assert health["weights"] and health["providerLoaded"] is False, health

        settings_reply = client.post("/settings", json={"pointDensity": 10 ** 9,
                                                        "bogus": 1}).get_json()
        assert settings_reply["settings"]["pointDensity"] == 76800, settings_reply
        assert settings_reply["notes"], "clamping went unreported"
        client.post("/settings", json={"pointDensity": 3000})

        capture = client.post("/capture").get_json()
        assert capture["cloud"]["points"] == 3000, capture
        assert capture["source"] == "fixture:person", capture

        ply = client.get("/cloud")
        assert ply.status_code == 200 and ply.data.startswith(b"ply\n"), ply.status_code
        stats = client.get("/cloud/stats").get_json()
        assert stats["cloud"]["points"] == 3000, stats
        state = client.get("/state").get_json()
        assert state["hasCloud"] and state["points"] == 3000, state
        state["settings"]["model"]                      # present for the panel
        return (f"7 routes, capture {capture['totalMs']} ms on "
                f"{capture['provider']}, PLY {len(ply.data) / 1e6:.2f} MB")

    def service_on_a_port():
        import requests
        from werkzeug.serving import make_server

        from reconstruction.server import create_app
        from reconstruction.service import Service

        server = make_server("127.0.0.1", 0, create_app(Service(), None),
                             threaded=True)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            base = f"http://127.0.0.1:{server.server_port}"
            health = requests.get(base + "/health", timeout=10).json()
            assert health["ok"], health
        finally:
            server.shutdown()
        return f"bound and answered on {base}/health"

    def live_frame():
        source = frames.FrameSource({"baseUrl": args.base_url,
                                     "robotId": args.robot_id})
        body = source.fetch(fresh=True)
        disparity, rgb = state["model"].infer(body)
        resolved, _ = settings_module.resolve({})
        _, _, stats = cloud.to_points(disparity, rgb, resolved)
        assert stats["points"] > 100, stats
        return (f"{len(body)} B from {source.snap_url}, "
                f"{stats['points']} points, {source.stats['fetchMs']} ms fetch")

    gate.step("environment and providers", environment)
    gate.step("depth weights present", weights_present)
    gate.step("DPT preprocessing rule", preprocessing)
    gate.step("inference on a photograph", inference_on_photograph)
    gate.step("CPU fallback provider", cpu_fallback)
    gate.step("depth on known room geometry", room_geometry)
    gate.step("disparity to point cloud", cloud_geometry)
    gate.step("point density setting", density_setting)
    gate.step("settings clamp instead of raising", settings_clamps)
    gate.step("PLY written and readable", ply_written)
    gate.step("binary wire frame for the viewer", wire_frame_format)
    gate.step("preview image", preview_image)
    gate.step("capture path against a stub adapter", capture_path_stubbed)
    gate.step("sidecar endpoints", service_endpoints)
    gate.step("sidecar binds a real port", service_on_a_port)

    excluded = []
    if args.offline:
        excluded.append("live frame from the dog through the adapter's cache")
    else:
        gate.step("live frame from the dog through the adapter's cache",
                  live_frame)
    return gate.summary(excluded)


if __name__ == "__main__":
    raise SystemExit(main())
