"""User configuration persisted as JSON.

The configuration is split into small sections so the settings page and the
processing pipeline can consume independent pieces of it.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field, fields, is_dataclass
from enum import Enum
from typing import Any, Dict, List, Optional

from . import constants
from .exceptions import ConfigError
from .logger import get_logger

_log = get_logger("core.config")


class Language(Enum):
    ENGLISH = "en"
    PERSIAN = "fa"


class Theme(Enum):
    DARK = "dark"
    LIGHT = "light"


class AIEngineType(Enum):
    DISABLED = "disabled"
    LOCAL_EMBEDDING = "local_embedding"
    CLIP = "clip"


@dataclass
class GeneralSettings:
    language: Language = Language.PERSIAN
    theme: Theme = Theme.DARK
    start_with_windows: bool = False
    minimize_to_tray: bool = True


@dataclass
class ScanSettings:
    image_extensions: List[str] = field(
        default_factory=lambda: sorted(constants.DEFAULT_IMAGE_EXTENSIONS)
    )
    include_hidden_files: bool = False
    excluded_folders: List[str] = field(
        default_factory=lambda: sorted(constants.DEFAULT_EXCLUDED_FOLDERS)
    )
    min_file_size_mb: float = 0.0
    max_file_size_mb: float = 0.0  # 0 == no limit
    max_workers: int = 0  # 0 == auto


@dataclass
class SimilaritySettings:
    duplicate_threshold: float = constants.DEFAULT_DUPLICATE_THRESHOLD
    similar_threshold: float = constants.DEFAULT_SIMILAR_THRESHOLD
    ai_threshold: float = constants.DEFAULT_AI_THRESHOLD
    enable_histogram: bool = True
    enable_ssim: bool = True
    enable_feature_matching: bool = True
    feature_max_matches: int = 64


@dataclass
class CleanupSettings:
    method: constants.CleanupMethod = constants.CleanupMethod.QUARANTINE
    warn_before_permanent_delete: bool = True
    quarantine_auto_purge_days: int = 30


@dataclass
class AISettings:
    engine: AIEngineType = AIEngineType.DISABLED
    model_path: str = ""
    use_gpu: bool = False
    max_ram_mb: int = 2048


@dataclass
class AppConfig:
    general: GeneralSettings = field(default_factory=GeneralSettings)
    scan: ScanSettings = field(default_factory=ScanSettings)
    similarity: SimilaritySettings = field(default_factory=SimilaritySettings)
    cleanup: CleanupSettings = field(default_factory=CleanupSettings)
    ai: AISettings = field(default_factory=AISettings)
    last_scan_folders: List[str] = field(default_factory=list)

    # ------------------------------------------------------------------
    # (De)serialisation
    # ------------------------------------------------------------------

    def to_dict(self) -> Dict[str, Any]:
        return _to_plain_dict(asdict(self))

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AppConfig":
        config = cls()
        if not isinstance(data, dict):
            raise ConfigError("Configuration root must be a JSON object")
        for section_name, section_data in data.items():
            if section_name == "last_scan_folders":
                if isinstance(section_data, list):
                    config.last_scan_folders = [str(f) for f in section_data]
                continue
            section = getattr(config, section_name, None)
            if section is None or not isinstance(section_data, dict):
                continue
            for key, value in section_data.items():
                _set_field(section, key, value)
        return config

    # ------------------------------------------------------------------
    # Disk access
    # ------------------------------------------------------------------

    def save(self, path: Optional[str] = None) -> None:
        path = path or constants.config_path()
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            tmp_path = path + ".tmp"
            with open(tmp_path, "w", encoding="utf-8") as handle:
                json.dump(self.to_dict(), handle, ensure_ascii=False, indent=2)
            os.replace(tmp_path, path)
        except OSError as exc:
            raise ConfigError(f"Cannot write configuration to {path}") from exc

    @classmethod
    def load(cls, path: Optional[str] = None) -> "AppConfig":
        path = path or constants.config_path()
        if not os.path.exists(path):
            _log.info("Configuration file missing, using defaults at %s", path)
            return cls()
        try:
            with open(path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
        except (OSError, json.JSONDecodeError) as exc:
            raise ConfigError(f"Cannot read configuration from {path}") from exc
        return cls.from_dict(data)


def _to_plain_dict(value: Any) -> Any:
    """Recursively convert enums and tuples into plain JSON types."""
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {key: _to_plain_dict(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_to_plain_dict(item) for item in value]
    return value


def _set_field(section: Any, key: str, value: Any) -> None:
    if not is_dataclass(section) or not hasattr(section, key):
        return
    current = getattr(section, key)
    if isinstance(current, Enum):
        try:
            setattr(section, key, type(current)(value))
        except ValueError:
            _log.warning("Invalid enum value %s for %s, keeping default", value, key)
        return
    if isinstance(current, list):
        if isinstance(value, list):
            setattr(section, key, [str(item) for item in value])
        return
    if isinstance(current, bool):
        if isinstance(value, bool):
            setattr(section, key, value)
        return
    if isinstance(current, (int, float)) and not isinstance(current, bool):
        try:
            setattr(section, key, type(current)(value))
        except (TypeError, ValueError):
            _log.warning("Invalid numeric value %s for %s", value, key)
        return
    if isinstance(current, str):
        setattr(section, key, str(value))
