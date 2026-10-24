"""Frames to validate against when the dog is switched off.

Two of them, for two different jobs:

- `tests/fixtures/person.jpg` (the adapter's YOLO fixture, reused here) is
  a real photograph, so the depth map has to behave like one: the pavement
  at the bottom of the frame is nearer than the top of the frame.
- `synthetic_room()` draws a one-point-perspective room at QVGA, so the
  cloud can be checked against geometry that is known rather than guessed:
  the back wall is the far thing, the floor at the bottom edge is the near
  thing. Drawn in code, so no binary lands in the repo and the picture is
  the same on every machine.

Neither is a XIAO frame. "Vaguely resembles the room" (the phase 1
done-when) needs the real camera and is checked with `--with-hardware`.
"""
from pathlib import Path

import numpy as np

QVGA = (320, 240)
PERSON_JPG = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "person.jpg"


def synthetic_room(size: tuple[int, int] = QVGA, seed: int = 0) -> bytes:
    """A boxy room seen head-on, as JPEG bytes: floor, ceiling, two side
    walls receding to a back wall, and a crate on the floor."""
    from PIL import Image, ImageDraw

    width, height = size
    image = Image.new("RGB", size, (150, 150, 155))
    draw = ImageDraw.Draw(image)

    # Back wall: a rectangle in the middle, the vanishing plane.
    wall = [width * 0.30, height * 0.28, width * 0.70, height * 0.72]
    draw.rectangle(wall, fill=(128, 126, 132))

    # Floor, ceiling and side walls as trapezia running out to the corners.
    draw.polygon([(0, height), (width, height),
                  (wall[2], wall[3]), (wall[0], wall[3])], fill=(96, 84, 72))
    draw.polygon([(0, 0), (width, 0),
                  (wall[2], wall[1]), (wall[0], wall[1])], fill=(170, 170, 175))
    draw.polygon([(0, 0), (wall[0], wall[1]),
                  (wall[0], wall[3]), (0, height)], fill=(140, 138, 144))
    draw.polygon([(width, 0), (wall[2], wall[1]),
                  (wall[2], wall[3]), (width, height)], fill=(140, 138, 144))

    # Floorboards and a crate give the model edges to work with.
    for step in range(1, 7):
        y = wall[3] + (height - wall[3]) * (step / 6.0) ** 1.6
        draw.line([(0, y), (width, y)], fill=(80, 70, 60), width=1)
    crate = [width * 0.44, height * 0.63, width * 0.60, height * 0.84]
    draw.rectangle(crate, fill=(154, 120, 78), outline=(60, 45, 30), width=2)
    draw.line([crate[0], crate[1], crate[2], crate[3]], fill=(70, 55, 38))

    # A little grain: a perfectly flat render is unlike any real camera.
    noise = np.random.default_rng(seed).normal(0, 3.0, (height, width, 1))
    grained = np.clip(np.asarray(image, dtype=np.float32) + noise, 0, 255)
    image = Image.fromarray(grained.astype(np.uint8))

    return _jpeg(image)


def person_frame() -> bytes:
    """The adapter's committed YOLO fixture, reused as a real photograph."""
    return PERSON_JPG.read_bytes()


def _jpeg(image) -> bytes:
    import io

    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=88)
    return buffer.getvalue()
