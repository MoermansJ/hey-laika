"""The reconstruction sidecar: one process, one port, one room.

    dog/reconstruction/.venv/Scripts/python dog/reconstruction/server.py
    ... --port 8766 --source adapter --base-url http://localhost:8080

Runs on the HOST, never in the adapter image (README.md says why). The
orchestrator reaches it over plain HTTP — on Jon's laptop that means the
PC's Tailscale address — and the viewer connects straight to it for cloud
data.

    GET  /health             liveness: provider, model, uptime
    GET  /state              what the service holds right now
    GET  /settings           current settings
    POST /settings           merge settings; always 200, clamps reported
    POST /capture            one frame -> one cloud, returns the stats
    GET  /cloud              the newest cloud as binary PLY
    GET  /cloud/stats        the newest cloud's numbers, no payload
    GET  /models             which depth models exist and which are on disk
    GET  /                   the three.js viewer (viewer/index.html)
    WS   /ws/cloud           binary cloud frames, newest first on connect

Where frames come from is a setting, not a flag: POST /settings can move
the service between the fixture and a live adapter, or repoint it at
another Tailscale address, without a restart.

The viewer page and its websocket arrive with AGENT-24; the routes above
are the contract the orchestrator and the validation gate code against.
Flask's threaded dev server is deliberate: this serves one demo on a LAN,
not the public internet.
"""
import argparse
import io
import logging
import queue
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE.parent) not in sys.path:
    sys.path.insert(0, str(HERE.parent))

from flask import Flask, jsonify, request, send_file, send_from_directory  # noqa: E402
from flask_sock import Sock  # noqa: E402

from reconstruction import frames  # noqa: E402
from reconstruction import settings as settings_module  # noqa: E402
from reconstruction.service import Service  # noqa: E402

logger = logging.getLogger(__name__)

DEFAULT_PORT = 8766        # fruitfly's sim sits on 8765
VIEWER_DIR = HERE / "viewer"
KEEPALIVE_S = 25.0


def create_app(service: Service) -> Flask:
    app = Flask(__name__, static_folder=str(VIEWER_DIR), static_url_path="")
    app.config["SERVICE"] = service
    sock = Sock(app)

    @app.get("/health")
    def health():
        model = service.model()
        return jsonify({"service": "reconstruction", "ok": True,
                        "model": service.settings["model"],
                        "source": service.settings["source"],
                        "provider": model.expected_provider,
                        "providerLoaded": model.loaded,
                        "weights": model.available,
                        "uptimeS": service.state()["uptimeS"]})

    @app.get("/state")
    def state():
        return jsonify(service.state())

    @app.get("/settings")
    def get_settings():
        return jsonify({"settings": service.settings, "notes": service.notes})

    @app.post("/settings")
    def post_settings():
        resolved, notes = service.update_settings(request.get_json(silent=True) or {})
        return jsonify({"settings": resolved, "notes": notes})

    @app.post("/capture")
    def capture():
        try:
            return jsonify(service.capture())
        except frames.FrameError as error:
            service.last_error = str(error)
            logger.warning("Capture failed: %s", error)
            return jsonify({"error": "frame", "detail": str(error)}), 502
        except FileNotFoundError as error:          # weights not downloaded
            service.last_error = str(error)
            return jsonify({"error": "weights", "detail": str(error)}), 503

    @app.get("/cloud")
    def cloud_ply():
        from reconstruction import cloud as cloud_module

        current = service.current_cloud()
        if current is None:
            return jsonify({"error": "empty", "detail": "no capture yet"}), 404
        buffer = io.BytesIO()
        path = cloud_module.write_ply(HERE / "out" / "current.ply", *current)
        buffer.write(path.read_bytes())
        buffer.seek(0)
        return send_file(buffer, mimetype="application/octet-stream",
                         as_attachment=True, download_name="room.ply")

    @app.get("/models")
    def models():
        from reconstruction import depth

        return jsonify({"models": sorted(settings_module.MODELS),
                        "onDisk": sorted(name for name in settings_module.MODELS
                                         if depth.build_model(name).available),
                        "current": service.settings["model"]})

    @app.get("/")
    def viewer():
        return send_from_directory(VIEWER_DIR, "index.html")

    @sock.route("/ws/cloud")
    def cloud_socket(ws):
        """One queue per viewer, latest cloud wins: a slow tab must never
        hold up a capture, and an old cloud is worth nothing once a newer
        one exists. The capture thread enqueues; this thread sends."""
        outbox = queue.Queue(maxsize=2)

        def listener(blob: bytes) -> None:
            if outbox.full():
                outbox.get_nowait()
            outbox.put_nowait(blob)

        current = service.binary_frame()
        if current is not None:
            ws.send(current)
        service.subscribe(listener)
        logger.info("Viewer connected")
        try:
            while True:
                try:
                    ws.send(outbox.get(timeout=KEEPALIVE_S))
                except queue.Empty:
                    ws.send('{"type":"ping"}')
        except Exception:                            # noqa: BLE001 - tab closed
            pass
        finally:
            service.unsubscribe(listener)
            logger.info("Viewer disconnected")

    @app.get("/cloud/stats")
    def cloud_stats():
        last = service.last_capture
        if last is None:
            return jsonify({"error": "empty", "detail": "no capture yet"}), 404
        return jsonify(last)

    return app


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--host", default="0.0.0.0",
                        help="0.0.0.0 so the laptop can reach it over Tailscale")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--source", default="fixture", choices=["fixture", "adapter"],
                        help="where frames come from; fixture needs no dog")
    parser.add_argument("--base-url", default=frames.DEFAULTS["baseUrl"],
                        help="orchestrator or adapter base URL for --source adapter")
    parser.add_argument("--robot-id", default=frames.DEFAULTS["robotId"])
    parser.add_argument("--model", default=None, help="depth model name")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")
    overrides = {"source": args.source, "frameBaseUrl": args.base_url,
                 "robotId": args.robot_id}
    if args.model:
        overrides["model"] = args.model
    service = Service(overrides)
    app = create_app(service)
    print(f"Reconstruction serving http://{args.host}:{args.port}/ "
          f"(viewer; source {args.source}, model {service.settings['model']})")
    app.run(host=args.host, port=args.port, threaded=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
