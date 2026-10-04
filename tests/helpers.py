"""Shared test fixtures: a temporary folder of images with known duplicates."""

from __future__ import annotations

import os
import shutil
import tempfile
import uuid
from typing import Tuple

# Fixture folders live under the repository rather than the system temp dir:
# ``C:\...\AppData\Local\Temp`` is a protected location for the cleanup service,
# and flat temp paths would make the quarantine tests impossible to run.
_PROJECT_TMP = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".test_tmp")


def make_image(directory: str, name: str, color: Tuple[int, int, int], size: int = 64) -> str:
    """Write a flat-colour PNG and return its path (PIL is a test dependency)."""
    from PIL import Image

    path = os.path.join(directory, name)
    Image.new("RGB", (size, size), color).save(path, format="PNG")
    return path


def _structured_image(path: str, seed: int) -> str:
    """An image with real edges/gradients - flat colours hash to zero with pHash."""
    import numpy as np
    from PIL import Image

    rng = np.random.default_rng(seed)
    data = rng.integers(0, 255, size=(200, 200, 3), dtype=np.uint8)
    Image.fromarray(data, "RGB").save(path, format="JPEG", quality=90)
    return path


def duplicate_set(root: str) -> dict:
    """Create a folder whose contents have a known duplicate structure.

    Returns a dict describing the layout so tests can assert on it:

    * ``original`` and ``copy`` are byte-identical (same content, same name)
    * ``resized`` is a re-encoded smaller version of ``original``
    * ``other`` is an unrelated image
    """
    from PIL import Image

    folder = os.path.join(root, "photos")
    os.makedirs(folder, exist_ok=True)

    original = os.path.join(folder, "IMG_0001.jpg")
    Image.new("RGB", (200, 200), (120, 180, 240)).save(original, format="JPEG", quality=90)

    copy = os.path.join(folder, "IMG_0001_copy.jpg")
    shutil.copyfile(original, copy)

    resized = os.path.join(folder, "IMG_0001_small.jpg")
    with Image.open(original) as image:
        image.convert("RGB").resize((100, 100)).save(resized, format="JPEG", quality=60)

    other = _structured_image(os.path.join(folder, "DCP_9999.jpg"), seed=12345)

    return {
        "folder": folder,
        "original": original,
        "copy": copy,
        "resized": resized,
        "other": other,
    }


def temp_dir() -> str:
    os.makedirs(_PROJECT_TMP, exist_ok=True)
    path = os.path.join(_PROJECT_TMP, uuid.uuid4().hex)
    os.makedirs(path, exist_ok=True)
    return path


def remove_tree(path: str) -> None:
    shutil.rmtree(path, ignore_errors=True)
    # Drop the shared fixture folder once the last test directory is gone.
    if os.path.isdir(_PROJECT_TMP) and not os.listdir(_PROJECT_TMP):
        shutil.rmtree(_PROJECT_TMP, ignore_errors=True)
