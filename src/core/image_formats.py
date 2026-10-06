"""Discovery of the image formats this Pillow installation can actually decode.

The scan pipeline selects candidate files purely by extension, so a format that
Pillow cannot open (notably HEIC/HEIF, which needs the optional ``pillow-heif``
plugin) would be counted as an image and then vanish silently when the decode
fails. Centralising the capability check here keeps that a single, explained
decision instead of a scattered set of silent skips.
"""

from __future__ import annotations

from typing import AbstractSet, Set

from .logger import get_logger

_log = get_logger("core.formats")

# HEIC/HEIF support is optional: register the plugin when it is installed so
# .heic/.heif files decode normally, and let the capability check below report
# honestly when it is not.
_HEIF_AVAILABLE = False
try:
    import pillow_heif  # type: ignore[import-not-found]

    pillow_heif.register_heif_opener()
    _HEIF_AVAILABLE = True
except ImportError:
    pass
except Exception as exc:  # a broken plugin install must never block the app
    _log.debug("pillow-heif is installed but unusable: %s", exc)


def heif_available() -> bool:
    """Whether HEIC/HEIF files can be decoded in this environment."""
    return _HEIF_AVAILABLE


def decodable_extensions(requested: AbstractSet[str]) -> Set[str]:
    """Intersect ``requested`` extensions with the ones Pillow can decode.

    Returns the subset of ``requested`` that maps to a registered Pillow
    opener. Callers should log the difference so a missing optional codec is
    reported to the user rather than silently dropping their photos.
    """
    try:
        from PIL import Image
    except ImportError:  # pragma: no cover - Pillow is a hard dependency
        return set(requested)

    return {ext for ext in requested if ext in Image.registered_extensions()}


def unsupported_extensions(requested: AbstractSet[str]) -> Set[str]:
    """The extensions from ``requested`` this environment cannot decode."""
    try:
        from PIL import Image
    except ImportError:  # pragma: no cover
        return set()
    return set(requested) - decodable_extensions(requested)
