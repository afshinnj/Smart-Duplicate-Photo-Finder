"""Translation support.

Loads ``fa.json`` / ``en.json`` next to this module and exposes a process-wide
:class:`Translator`. Widgets call :func:`tr` to resolve a key, and reconnect to
``Translator.language_changed`` when the user picks another language so the whole
window can be re-rendered without a restart.

Persian is right-to-left; :func:`is_rtl` lets the window flip its layout
direction and text alignment accordingly.
"""

from __future__ import annotations

import json
import os
from typing import Dict, List, Optional

from PySide6.QtCore import QCoreApplication, QObject, Qt, Signal

from ..core.logger import get_logger

_log = get_logger("i18n")

_DEFAULT_LANGUAGE = "fa"
_LANGUAGE_FILES = {"fa": "fa.json", "en": "en.json"}
_LANGUAGE_NAMES = {"fa": "فارسی", "en": "English"}
_RTL_LANGUAGES = frozenset({"fa", "ar", "he", "ur"})

# Keys that may appear with ``{placeholders}`` - kept here only as documentation.
_FORMAT_KEYS = frozenset({"results_groups_count", "cleanup_files", "cleanup_undo_done"})


class Translator(QObject):
    """Holds the strings of the active language and broadcasts changes."""

    language_changed = Signal()

    def __init__(self, language: str = _DEFAULT_LANGUAGE) -> None:
        super().__init__()
        self._language = _DEFAULT_LANGUAGE
        self._strings: Dict[str, str] = {}
        self.load(language)

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------

    def load(self, language: str) -> bool:
        """Switch to ``language``. Unknown languages keep the previous one."""
        filename = _LANGUAGE_FILES.get(language)
        if filename is None:
            _log.warning("Unknown language %r, keeping %s", language, self._language)
            return False

        path = os.path.join(os.path.dirname(__file__), filename)
        try:
            with open(path, "r", encoding="utf-8") as handle:
                strings = json.load(handle)
        except (OSError, json.JSONDecodeError) as exc:
            _log.error("Cannot load translations from %s: %s", path, exc)
            return False

        if not isinstance(strings, dict):
            _log.error("Translation file %s is not an object", path)
            return False

        self._language = language
        self._strings = {str(key): str(value) for key, value in strings.items()}
        _log.info("Loaded %d strings for language %s", len(self._strings), language)
        return True

    def set_language(self, language: str) -> bool:
        """Load ``language`` and notify listeners when it actually changed."""
        if language == self._language:
            return True
        if not self.load(language):
            return False
        self.language_changed.emit()
        return True

    # ------------------------------------------------------------------
    # Lookups
    # ------------------------------------------------------------------

    def tr(self, key: str, default: Optional[str] = None, **kwargs: object) -> str:
        """Resolve ``key`` and interpolate ``{name}`` placeholders.

        Missing keys fall back to ``default`` (or the key itself) and are logged
        once so missing translations are easy to spot during development.
        """
        text = self._strings.get(key)
        if text is None:
            if key not in _reported_missing:
                _reported_missing.add(key)
                _log.warning("Missing translation key: %s", key)
            text = default if default is not None else key
        if kwargs:
            try:
                return text.format(**kwargs)
            except (KeyError, IndexError):
                return text
        return text

    def has(self, key: str) -> bool:
        return key in self._strings

    @property
    def language(self) -> str:
        return self._language

    @property
    def language_name(self) -> str:
        return _LANGUAGE_NAMES.get(self._language, self._language)

    @property
    def is_rtl(self) -> bool:
        return self._language in _RTL_LANGUAGES

    @property
    def layout_direction(self) -> Qt.LayoutDirection:
        return Qt.RightToLeft if self.is_rtl else Qt.LeftToRight

    def available_languages(self) -> List[str]:
        return list(_LANGUAGE_FILES)


_reported_missing: set = set()


# ---------------------------------------------------------------------------
# Process-wide singleton
# ---------------------------------------------------------------------------

_translator: Optional[Translator] = None


def translator() -> Translator:
    """Return the shared translator, creating it on first use."""
    global _translator
    if _translator is None:
        _translator = Translator()
    return _translator


def tr(key: str, default: Optional[str] = None, **kwargs: object) -> str:
    """Translate ``key`` using the shared translator."""
    return translator().tr(key, default, **kwargs)


def is_rtl() -> bool:
    return translator().is_rtl


def available_languages() -> List[str]:
    return list(_LANGUAGE_FILES)


def language_name(code: str) -> str:
    return _LANGUAGE_NAMES.get(code, code)


def qt_tr(context: str, source: str) -> str:
    """Qt-native translation hook, kept for completeness."""
    return QCoreApplication.translate(context, source)
