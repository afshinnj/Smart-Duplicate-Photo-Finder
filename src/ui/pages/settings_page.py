"""Settings page.

Every control is bound directly to the shared :class:`~core.config.AppConfig`;
``Save`` persists it to disk (and applies what can be applied live, such as the
language and theme).
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ...ai.ai_engine import AIEngineRegistry
from ...core.config import AIEngineType, Language, Theme
from ...core.constants import CleanupMethod
from ...core.logger import get_logger
from ...i18n import available_languages, language_name, tr

_log = get_logger("ui.settings_page")


class SettingsPage(QWidget):
    """All user-tunable options grouped into sections."""

    language_changed = Signal(str)
    theme_changed = Signal(object)

    def __init__(self, context, parent=None) -> None:
        super().__init__(parent)
        self._context = context
        self._build()
        self._load_values()

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 24)
        root.setSpacing(14)

        self._title = QLabel(tr("nav_settings"), self)
        self._title.setObjectName("PageTitle")
        root.addWidget(self._title)

        # The page is taller than the viewport; a scroll area keeps every row at
        # its real height instead of letting the top-level layout crush them.
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        content = QWidget(scroll)
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(14)

        content_layout.addWidget(self._build_general())
        content_layout.addWidget(self._build_scan())
        content_layout.addWidget(self._build_similarity())
        content_layout.addWidget(self._build_cleanup())
        content_layout.addWidget(self._build_ai())

        actions = QHBoxLayout()
        actions.addStretch()
        self._btn_save = QPushButton(tr("settings_save"), content)
        self._btn_save.setMinimumHeight(40)
        self._btn_save.setMinimumWidth(140)
        self._btn_save.clicked.connect(self.save)
        actions.addWidget(self._btn_save)
        content_layout.addLayout(actions)

        content_layout.addStretch()
        scroll.setWidget(content)
        root.addWidget(scroll, stretch=1)

    def _build_general(self) -> QGroupBox:
        box = QGroupBox(tr("settings_general"), self)
        form = self._make_form(box)

        self._language = QComboBox(box)
        for code in available_languages():
            self._language.addItem(language_name(code), code)
        form.addRow(tr("settings_language"), self._language)

        self._theme = QComboBox(box)
        self._theme.addItem(tr("settings_theme_dark"), Theme.DARK)
        self._theme.addItem(tr("settings_theme_light"), Theme.LIGHT)
        form.addRow(tr("settings_theme"), self._theme)

        self._start_with_windows = QCheckBox(box)
        form.addRow(tr("settings_start_with_windows"), self._start_with_windows)

        self._minimize_to_tray = QCheckBox(box)
        form.addRow(tr("settings_minimize_to_tray"), self._minimize_to_tray)
        return box

    def _build_scan(self) -> QGroupBox:
        box = QGroupBox(tr("settings_scan"), self)
        form = self._make_form(box)

        self._min_size = QDoubleSpinBox(box)
        self._min_size.setRange(0.0, 1024.0)
        self._min_size.setDecimals(1)
        self._min_size.setSuffix(" MB")
        form.addRow(tr("scan_min_size"), self._min_size)

        self._max_size = QDoubleSpinBox(box)
        self._max_size.setRange(0.0, 10240.0)
        self._max_size.setDecimals(1)
        self._max_size.setSuffix(" MB")
        form.addRow(tr("scan_max_size"), self._max_size)

        self._include_hidden = QCheckBox(box)
        form.addRow(tr("scan_include_hidden"), self._include_hidden)

        self._extensions = QLineEdit(box)
        self._extensions.setPlaceholderText("jpg; png; webp; ...")
        form.addRow(tr("scan_formats"), self._extensions)

        self._excluded = QLineEdit(box)
        self._excluded.setPlaceholderText("Windows; Program Files; ...")
        form.addRow(tr("scan_excluded_folders"), self._excluded)

        self._workers = QSpinBox(box)
        self._workers.setRange(0, 32)
        self._workers.setSpecialValueText(tr("settings_workers_auto"))
        form.addRow(tr("settings_max_workers"), self._workers)
        return box

    def _build_similarity(self) -> QGroupBox:
        box = QGroupBox(tr("settings_similarity"), self)
        form = self._make_form(box)

        self._duplicate_threshold = self._make_percent_spin(box)
        form.addRow(tr("settings_duplicate_threshold"), self._duplicate_threshold)

        self._similar_threshold = self._make_percent_spin(box)
        form.addRow(tr("settings_similar_threshold"), self._similar_threshold)

        self._ai_threshold = self._make_percent_spin(box)
        form.addRow(tr("settings_ai_threshold"), self._ai_threshold)

        self._histogram = QCheckBox(box)
        form.addRow(tr("settings_enable_histogram"), self._histogram)

        self._ssim = QCheckBox(box)
        form.addRow(tr("settings_enable_ssim"), self._ssim)

        self._features = QCheckBox(box)
        form.addRow(tr("settings_enable_features"), self._features)

        self._max_matches = QSpinBox(box)
        self._max_matches.setRange(1, 512)
        form.addRow(tr("settings_max_matches"), self._max_matches)
        return box

    def _build_cleanup(self) -> QGroupBox:
        box = QGroupBox(tr("settings_cleanup"), self)
        form = self._make_form(box)

        self._cleanup_method = QComboBox(box)
        self._cleanup_method.addItem(tr("cleanup_quarantine"), CleanupMethod.QUARANTINE)
        self._cleanup_method.addItem(tr("cleanup_move_recycle"), CleanupMethod.RECYCLE_BIN)
        self._cleanup_method.addItem(tr("cleanup_permanent"), CleanupMethod.PERMANENT)
        form.addRow(tr("settings_cleanup_method"), self._cleanup_method)

        self._warn_permanent = QCheckBox(box)
        form.addRow(tr("settings_permanent_warning"), self._warn_permanent)

        self._quarantine_days = QSpinBox(box)
        self._quarantine_days.setRange(0, 365)
        self._quarantine_days.setSuffix(" " + tr("settings_quarantine_days"))
        form.addRow(tr("settings_quarantine_days"), self._quarantine_days)
        return box

    def _build_ai(self) -> QGroupBox:
        box = QGroupBox(tr("settings_ai"), self)
        form = self._make_form(box)

        self._ai_enabled = QCheckBox(box)
        self._ai_enabled.toggled.connect(self._update_ai_state)
        form.addRow(tr("settings_enable_ai"), self._ai_enabled)

        self._ai_engine = QComboBox(box)
        self._ai_engine.addItem(tr("settings_ai_engine"), AIEngineType.LOCAL_EMBEDDING)
        self._ai_engine.addItem("CLIP", AIEngineType.CLIP)
        form.addRow(tr("settings_ai_engine"), self._ai_engine)

        self._ai_status = QLabel("", box)
        self._ai_status.setObjectName("DimLabel")
        self._ai_status.setWordWrap(True)
        form.addRow("", self._ai_status)

        self._model_path = QLineEdit(box)
        self._model_path.setPlaceholderText(tr("settings_model_path"))
        model_row = QHBoxLayout()
        model_row.setContentsMargins(0, 0, 0, 0)
        model_row.addWidget(self._model_path, stretch=1)
        self._btn_browse = QPushButton("…", box)
        self._btn_browse.setObjectName("SecondaryButton")
        self._btn_browse.setFixedWidth(32)
        self._btn_browse.clicked.connect(self._browse_model)
        model_row.addWidget(self._btn_browse)
        form.addRow(tr("settings_model_path"), model_row)

        self._use_gpu = QCheckBox(box)
        form.addRow(tr("settings_use_gpu"), self._use_gpu)

        self._max_ram = QSpinBox(box)
        self._max_ram.setRange(256, 32768)
        self._max_ram.setSuffix(" MB")
        form.addRow(tr("settings_max_ram"), self._max_ram)
        return box

    @staticmethod
    def _make_form(parent) -> QFormLayout:
        """A form whose field column always grows to fill the available width."""
        form = QFormLayout(parent)
        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        # On narrow windows, drop the field below its label instead of clipping.
        form.setRowWrapPolicy(QFormLayout.WrapLongRows)
        form.setHorizontalSpacing(16)
        form.setVerticalSpacing(10)
        return form

    @staticmethod
    def _make_percent_spin(parent) -> QDoubleSpinBox:
        spin = QDoubleSpinBox(parent)
        spin.setRange(0.0, 100.0)
        spin.setDecimals(1)
        spin.setSingleStep(1.0)
        spin.setSuffix(" %")
        return spin

    # ------------------------------------------------------------------
    # Values
    # ------------------------------------------------------------------

    def _load_values(self) -> None:
        config = self._context.config
        general = config.general
        scan = config.scan
        similarity = config.similarity
        cleanup = config.cleanup
        ai = config.ai

        self._language.setCurrentIndex(
            max(0, self._language.findData(general.language.value))
        )
        self._theme.setCurrentIndex(max(0, self._theme.findData(general.theme)))
        self._start_with_windows.setChecked(general.start_with_windows)
        self._minimize_to_tray.setChecked(general.minimize_to_tray)

        self._min_size.setValue(scan.min_file_size_mb)
        self._max_size.setValue(scan.max_file_size_mb)
        self._include_hidden.setChecked(scan.include_hidden_files)
        self._extensions.setText("; ".join(scan.image_extensions))
        self._excluded.setText("; ".join(scan.excluded_folders))
        self._workers.setValue(scan.max_workers)

        self._duplicate_threshold.setValue(similarity.duplicate_threshold)
        self._similar_threshold.setValue(similarity.similar_threshold)
        self._ai_threshold.setValue(similarity.ai_threshold)
        self._histogram.setChecked(similarity.enable_histogram)
        self._ssim.setChecked(similarity.enable_ssim)
        self._features.setChecked(similarity.enable_feature_matching)
        self._max_matches.setValue(similarity.feature_max_matches)

        self._cleanup_method.setCurrentIndex(
            max(0, self._cleanup_method.findData(cleanup.method))
        )
        self._warn_permanent.setChecked(cleanup.warn_before_permanent_delete)
        self._quarantine_days.setValue(cleanup.quarantine_auto_purge_days)

        self._ai_enabled.setChecked(ai.engine != AIEngineType.DISABLED)
        self._ai_engine.setCurrentIndex(
            max(0, self._ai_engine.findData(ai.engine))
        )
        self._model_path.setText(ai.model_path)
        self._use_gpu.setChecked(ai.use_gpu)
        self._max_ram.setValue(ai.max_ram_mb)
        self._update_ai_state()

    def _update_ai_state(self) -> None:
        enabled = self._ai_enabled.isChecked()
        self._ai_engine.setEnabled(enabled)
        self._model_path.setEnabled(enabled)
        self._btn_browse.setEnabled(enabled)
        self._use_gpu.setEnabled(enabled)
        self._max_ram.setEnabled(enabled)
        self._ai_status.setText(self._ai_availability_text() if enabled else "")

    def _ai_availability_text(self) -> str:
        reasons = []
        for info in AIEngineRegistry.describe_all():
            if info.unavailable_reason:
                reasons.append(f"{info.engine_type.value}: {info.unavailable_reason}")
        if not reasons:
            return ""
        return tr("settings_ai_unavailable", reason="; ".join(reasons))

    def _browse_model(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, tr("settings_model_path"))
        if path:
            self._model_path.setText(path)

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def save(self) -> None:
        config = self._context.config
        general = config.general
        scan = config.scan
        similarity = config.similarity
        cleanup = config.cleanup
        ai = config.ai

        language_code = self._language.currentData()
        new_language = Language(language_code) if language_code else general.language
        new_theme = self._theme.currentData() or general.theme

        general.language = new_language
        general.theme = new_theme
        general.start_with_windows = self._start_with_windows.isChecked()
        general.minimize_to_tray = self._minimize_to_tray.isChecked()

        scan.min_file_size_mb = self._min_size.value()
        scan.max_file_size_mb = self._max_size.value()
        scan.include_hidden_files = self._include_hidden.isChecked()
        extensions = [
            part.strip().lower().lstrip(".")
            for part in self._extensions.text().split(";")
            if part.strip()
        ]
        if extensions:
            scan.image_extensions = sorted({f".{ext}" for ext in extensions})
        excluded = [part.strip() for part in self._excluded.text().split(";") if part.strip()]
        if excluded:
            scan.excluded_folders = excluded
        scan.max_workers = self._workers.value()

        similarity.duplicate_threshold = self._duplicate_threshold.value()
        similarity.similar_threshold = self._similar_threshold.value()
        similarity.ai_threshold = self._ai_threshold.value()
        similarity.enable_histogram = self._histogram.isChecked()
        similarity.enable_ssim = self._ssim.isChecked()
        similarity.enable_feature_matching = self._features.isChecked()
        similarity.feature_max_matches = self._max_matches.value()

        cleanup.method = self._cleanup_method.currentData() or cleanup.method
        cleanup.warn_before_permanent_delete = self._warn_permanent.isChecked()
        cleanup.quarantine_auto_purge_days = self._quarantine_days.value()

        if self._ai_enabled.isChecked():
            ai.engine = self._ai_engine.currentData() or AIEngineType.LOCAL_EMBEDDING
        else:
            ai.engine = AIEngineType.DISABLED
        ai.model_path = self._model_path.text().strip()
        ai.use_gpu = self._use_gpu.isChecked()
        ai.max_ram_mb = self._max_ram.value()

        self._context.save_config()
        _log.info("Settings saved")

        self.language_changed.emit(new_language.value)
        self.theme_changed.emit(new_theme)
        QMessageBox.information(self, tr("nav_settings"), tr("settings_saved"))

    # ------------------------------------------------------------------
    # Retranslation
    # ------------------------------------------------------------------

    def retranslate(self) -> None:
        self._title.setText(tr("nav_settings"))
        self._btn_save.setText(tr("settings_save"))
        self._theme.setItemText(0, tr("settings_theme_dark"))
        self._theme.setItemText(1, tr("settings_theme_light"))
        self._cleanup_method.setItemText(0, tr("cleanup_quarantine"))
        self._cleanup_method.setItemText(1, tr("cleanup_move_recycle"))
        self._cleanup_method.setItemText(2, tr("cleanup_permanent"))
        self._update_ai_state()
