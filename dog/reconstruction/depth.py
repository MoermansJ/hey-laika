"""Monocular depth on the host: one JPEG -> one relative depth map.

Pipeline (FLY_VIEW_BRIEF.md §Phase 1, step 1a):

  XIAO frame (QVGA JPEG)  ->  DPT preprocessing (resize to a multiple of 14
  keeping the aspect ratio, ImageNet normalisation)  ->  Depth Anything V2
  through onnxruntime  ->  disparity, resized back to the frame's own size.

The model emits *relative inverse depth* (disparity): larger means nearer,
and the units are arbitrary. Turning that into metres is cloud.py's job,
and getting it actually right is phase 5's.

Provider: DirectML first, CPU second. The PC is an AMD RX 5700 XT, so there
is no CUDA path, and the adapter container cannot see the GPU at all —
which is why this runs as a host-native sidecar rather than inside the
image (see the feasibility report in the design doc). The chosen provider
and the per-run timing are reported in `stats` so a slow demo can be
diagnosed without guessing.

The session loads on first use and the detector is injectable, so tests and
the validation script can run the surrounding code without the weights,
mirroring eyes.py's YoloOnnxDetector.
"""
import io
import logging
import threading
import time
from pathlib import Path

logger = logging.getLogger(__name__)

MODELS_DIR = Path(__file__).resolve().parent.parent / "models"

# DPT preprocessing constants, from the model's preprocessor_config.json.
TARGET_SIZE = 518
MULTIPLE_OF = 14
IMAGE_MEAN = (0.485, 0.456, 0.406)
IMAGE_STD = (0.229, 0.224, 0.225)

PREFERRED_PROVIDERS = ("DmlExecutionProvider", "CUDAExecutionProvider",
                       "CPUExecutionProvider")


def resize_for_dpt(width: int, height: int, target: int = TARGET_SIZE,
                   multiple: int = MULTIPLE_OF) -> tuple[int, int]:
    """The model's own resize rule: scale so the side that needs the least
    change lands on `target`, then round both sides to a multiple of 14."""
    scale_w, scale_h = target / width, target / height
    scale = scale_w if abs(1 - scale_w) < abs(1 - scale_h) else scale_h

    def constrain(value: float) -> int:
        return max(multiple, int(round(value * scale / multiple) * multiple))

    return constrain(width), constrain(height)


class DepthAnythingOnnx:
    """Depth Anything V2 through onnxruntime; loads on first use."""

    def __init__(self, model_path: str | Path, providers: list[str] | None = None):
        self.model_path = Path(model_path)
        self.model_name = self.model_path.name
        self.available = self.model_path.is_file()
        self.loaded = False
        self.provider = None
        self._requested = providers
        self._session = None
        self._input_name = None
        self._lock = threading.Lock()
        self.stats = {"runs": 0, "inferenceMs": None, "provider": None}

    def _load(self):
        with self._lock:
            if self._session is None:
                import onnxruntime as ort

                if not self.available:
                    raise FileNotFoundError(
                        f"{self.model_path} missing; run "
                        f"dog/tools/download_depth_model.py")
                installed = ort.get_available_providers()
                providers = self._requested or [p for p in PREFERRED_PROVIDERS
                                                if p in installed]
                if not providers:
                    providers = ["CPUExecutionProvider"]
                started = time.time()
                self._session = ort.InferenceSession(str(self.model_path),
                                                     providers=providers)
                self._input_name = self._session.get_inputs()[0].name
                self.provider = self._session.get_providers()[0]
                self.stats["provider"] = self.provider
                self.loaded = True
                logger.info("Depth: %s loaded in %.1fs on %s", self.model_name,
                            time.time() - started, self.provider)
            return self._session

    def infer(self, jpeg: bytes):
        """JPEG bytes -> (disparity HxW float32 at the frame's own size, rgb
        HxWx3 uint8). Larger disparity = nearer."""
        import numpy as np
        from PIL import Image

        session = self._load()
        image = Image.open(io.BytesIO(jpeg)).convert("RGB")
        width, height = image.size
        new_w, new_h = resize_for_dpt(width, height)
        resized = image.resize((new_w, new_h), Image.BICUBIC)

        tensor = np.asarray(resized, dtype=np.float32) / 255.0
        tensor = (tensor - np.array(IMAGE_MEAN, dtype=np.float32)) / \
            np.array(IMAGE_STD, dtype=np.float32)
        tensor = tensor.transpose(2, 0, 1)[None]        # NCHW
        if session.get_inputs()[0].type == "tensor(float16)":
            tensor = tensor.astype(np.float16)

        started = time.time()
        (output,) = session.run(None, {self._input_name: tensor})
        elapsed_ms = (time.time() - started) * 1000.0

        disparity = np.asarray(output, dtype=np.float32)
        while disparity.ndim > 2:                       # (1,H,W) or (1,1,H,W)
            disparity = disparity[0]
        # Back to the frame's own pixels, so cloud.py can pair depth with colour.
        disparity = np.asarray(
            Image.fromarray(disparity).resize((width, height), Image.BILINEAR),
            dtype=np.float32)

        self.stats["runs"] += 1
        self.stats["inferenceMs"] = round(elapsed_ms, 1)
        logger.debug("Depth: %dx%d in %.0f ms on %s", width, height,
                     elapsed_ms, self.provider)
        return disparity, np.asarray(image, dtype=np.uint8)


def build_model(name: str = "small", models_dir: Path | None = None,
                providers: list[str] | None = None) -> DepthAnythingOnnx:
    """A model by settings name (settings.MODELS), from dog/models/."""
    from reconstruction.settings import MODELS

    if name not in MODELS:
        raise ValueError(f"unknown depth model {name!r}; pick one of "
                         f"{sorted(MODELS)}")
    directory = Path(models_dir) if models_dir else MODELS_DIR
    return DepthAnythingOnnx(directory / MODELS[name], providers=providers)
