"""Discovery and loading of optional AI models.

Everything here is offline-first: models are only looked up in a local folder
inside the application data directory. Nothing is downloaded automatically and
no image data ever leaves the machine. A model that is not present simply makes
the corresponding engine report itself as unavailable.
"""

from __future__ import annotations

import glob
import importlib
import os
from typing import Any, Optional, Tuple

from ..core import constants
from ..core.logger import get_logger

_log = get_logger("ai.model_manager")

MODELS_DIR = os.path.join(constants.app_data_dir(), "models")

# Known small models that the user can drop into the models folder.
_KNOWN_EMBEDDING_MODELS = (
    "mobilenet_v3_small.onnx",
    "resnet18_embeddings.onnx",
    "clip_image_encoder.onnx",
)


def _lazy_import(module_name: str) -> Optional[Any]:
    """Import an optional dependency, returning ``None`` when it is absent."""
    try:
        return importlib.import_module(module_name)
    except Exception:
        return None


def models_directory() -> str:
    os.makedirs(MODELS_DIR, exist_ok=True)
    return MODELS_DIR


def available_model_files() -> list[str]:
    """ONNX model files that the user has placed in the models folder."""
    directory = models_directory()
    return sorted(os.path.basename(path) for path in glob.glob(os.path.join(directory, "*.onnx")))


def resolve_model_path(filename: str) -> Optional[str]:
    if not filename:
        return None
    candidate = (
        filename if os.path.isabs(filename) else os.path.join(models_directory(), filename)
    )
    return candidate if os.path.exists(candidate) else None


def load_embedding_model(model_path: str = "", use_gpu: bool = False) -> Tuple[Any, Any]:
    """Load an ONNX or TorchVision embedding model plus its preprocessing.

    Returns ``(model, preprocess)`` where ``preprocess`` maps a PIL image to a
    model input. Raises :class:`ImportError` when no backend is installed.
    """
    resolved = resolve_model_path(model_path) or _first_known_model()

    onnx = _lazy_import("onnxruntime")
    if onnx is not None and resolved:
        return _load_onnx(onnx, resolved, use_gpu)

    torch = _lazy_import("torch")
    torchvision = _lazy_import("torchvision")
    if torch is not None and torchvision is not None:
        return _load_torchvision(torch, torchvision)

    raise ImportError(
        "Neither onnxruntime nor (torch + torchvision) is installed; "
        "AI similarity is unavailable."
    )


def _first_known_model() -> Optional[str]:
    for filename in _KNOWN_EMBEDDING_MODELS:
        resolved = resolve_model_path(filename)
        if resolved:
            return resolved
    return None


def _model_file_available(model_path: str = "") -> bool:
    """Whether a local model file can actually be loaded right now."""
    if resolve_model_path(model_path) is not None:
        return True
    return _first_known_model() is not None


def _load_onnx(onnx: Any, model_path: str, use_gpu: bool) -> Tuple[Any, Any]:
    import numpy as np
    from PIL import Image

    _log.info("Loading ONNX embedding model %s", model_path)
    providers = ["CPUExecutionProvider"]
    if use_gpu and "CUDAExecutionProvider" in onnx.get_available_providers():
        providers.insert(0, "CUDAExecutionProvider")

    session = onnx.InferenceSession(model_path, providers=providers)
    input_name = session.get_inputs()[0].name

    def preprocess(image: Image.Image) -> Any:
        resized = image.resize((224, 224), Image.Resampling.LANCZOS)
        array = np.asarray(resized, dtype=np.float32) / 255.0
        array = (array - [0.485, 0.456, 0.406]) / [0.229, 0.224, 0.225]
        return np.transpose(array, (2, 0, 1)).astype(np.float32)

    def runner(tensor: Any) -> Any:
        if tensor.ndim != 4:
            tensor = tensor[np.newaxis, ...]
        return session.run(None, {input_name: tensor})[0]

    return runner, preprocess


def _load_torchvision(torch: Any, torchvision: Any) -> Tuple[Any, Any]:
    _log.info("Loading TorchVision embedding model")
    weights = torchvision.models.MobileNet_V3_Small_Weights.IMAGENET1K_V1
    model = torchvision.models.mobilenet_v3_small(weights=weights)
    model.eval()
    preprocess = torchvision.transforms.Compose(
        [
            torchvision.transforms.Resize((224, 224), antialias=True),
            torchvision.transforms.ToTensor(),
            torchvision.transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
        ]
    )

    def runner(tensor: Any) -> Any:
        with torch.no_grad():
            return model.features(tensor)

    return runner, preprocess
