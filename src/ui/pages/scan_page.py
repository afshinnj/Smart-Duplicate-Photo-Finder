"""Scan setup page.

Lets the user pick a target (whole computer, specific folders or removable
drives), tweak the scan options and then run the pipeline on a background thread
through :class:`~workers.scan_worker.ScanWorker`.
"""

from __future__ import annotations

from typing import List, Optional, Sequence

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QInputDialog,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ...core import system_info
from ...core.logger import get_logger
from ...models.scan_session import ScanSession
from ...services.progress import ProgressUpdate, format_duration, format_size
from ...workers.scan_worker import ScanWorker
from ...i18n import tr

_log = get_logger("ui.scan_page")


class ScanPage(QWidget):
    """Target selection, options and live progress for a running scan."""

    scan_started = Signal()
    scan_finished = Signal(object)  # ScanResult
    view_results_requested = Signal()

    def __init__(self, context, parent=None) -> None:
        super().__init__(parent)
        self._context = context
        self._worker: Optional[ScanWorker] = None
        self._build()
        self._reload_drives()
        self._restore_folders()

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 24)
        root.setSpacing(16)

        self._title = QLabel(tr("nav_scan"), self)
        self._title.setObjectName("PageTitle")
        self._subtitle = QLabel(tr("app_tagline"), self)
        self._subtitle.setObjectName("PageSubtitle")
        root.addWidget(self._title)
        root.addWidget(self._subtitle)

        # The target/options/progress stack is taller than most viewports; let it
        # scroll instead of collapsing every row to a sliver.
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        content = QWidget(scroll)
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(16)

        target_box, _target_layout = self._build_targets(content)
        content_layout.addWidget(target_box)

        content_layout.addWidget(self._build_options(content))
        content_layout.addWidget(self._build_progress(content))

        content_layout.addStretch()
        scroll.setWidget(content)
        root.addWidget(scroll, stretch=1)

    def _build_targets(self, parent) -> tuple:
        box = QGroupBox(tr("scan_select_folder"), parent)
        layout = QVBoxLayout(box)
        layout.setSpacing(10)

        self._combo_targets = QComboBox(box)
        self._combo_targets.addItem(tr("scan_entire_computer"), "drives")
        self._combo_targets.addItem(tr("scan_usb_drives"), "removable")
        self._combo_targets.addItem(tr("scan_select_folder"), "folders")
        self._combo_targets.currentIndexChanged.connect(self._target_changed)
        profile_row = QHBoxLayout()
        self._profile_combo = QComboBox(box)
        self._btn_save_profile = QPushButton(tr("scan_profile_save"), box)
        self._btn_save_profile.setObjectName("SecondaryButton")
        self._btn_delete_profile = QPushButton(tr("scan_profile_delete"), box)
        self._btn_delete_profile.setObjectName("SecondaryButton")
        self._btn_save_profile.clicked.connect(self._save_profile)
        self._btn_delete_profile.clicked.connect(self._delete_profile)
        self._profile_combo.currentIndexChanged.connect(self._load_selected_profile)
        profile_row.addWidget(self._profile_combo, stretch=1)
        profile_row.addWidget(self._btn_save_profile)
        profile_row.addWidget(self._btn_delete_profile)
        layout.addLayout(profile_row)
        layout.addWidget(self._combo_targets)
        self._refresh_profiles()

        # Folder list (shown for the "folders" target)
        self._folder_frame = QFrame(box)
        folder_layout = QVBoxLayout(self._folder_frame)
        folder_layout.setContentsMargins(0, 0, 0, 0)
        folder_layout.setSpacing(6)

        self._folder_list = QListWidget(self._folder_frame)
        self._folder_list.setMinimumHeight(110)
        self._folder_list.setAlternatingRowColors(True)
        folder_layout.addWidget(self._folder_list)

        buttons = QHBoxLayout(self._folder_frame)
        buttons.setSpacing(8)
        self._btn_add = QPushButton(tr("scan_add_folder"), self._folder_frame)
        self._btn_add.setObjectName("SecondaryButton")
        self._btn_remove = QPushButton(tr("scan_remove"), self._folder_frame)
        self._btn_remove.setObjectName("SecondaryButton")
        self._btn_add.clicked.connect(self._add_folder)
        self._btn_remove.clicked.connect(self._remove_folder)
        buttons.addWidget(self._btn_add)
        buttons.addWidget(self._btn_remove)
        buttons.addStretch()
        folder_layout.addLayout(buttons)
        layout.addWidget(self._folder_frame)

        # Drive checklist (shown for the "removable" target)
        self._drive_frame = QFrame(box)
        drive_layout = QVBoxLayout(self._drive_frame)
        drive_layout.setContentsMargins(0, 0, 0, 0)
        self._drive_list = QListWidget(self._drive_frame)
        self._drive_list.setMinimumHeight(110)
        drive_layout.addWidget(self._drive_list)
        layout.addWidget(self._drive_frame)

        warning = QLabel(tr("scan_full_disk_warning"), box)
        warning.setObjectName("DimLabel")
        warning.setWordWrap(True)
        layout.addWidget(warning)

        return box, layout

    def _build_options(self, parent) -> QGroupBox:
        box = QGroupBox(tr("scan_options"), parent)
        grid = QGridLayout(box)
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(10)

        self._check_hidden = QCheckBox(tr("scan_include_hidden"), box)
        grid.addWidget(self._check_hidden, 0, 0, 1, 2)

        self._min_label = QLabel(tr("scan_min_size"), box)
        self._min_spin = QDoubleSpinBox(box)
        self._min_spin.setRange(0.0, 1024.0)
        self._min_spin.setSingleStep(0.5)
        self._min_spin.setDecimals(1)
        self._min_spin.setSuffix(" MB")
        grid.addWidget(self._min_label, 1, 0)
        grid.addWidget(self._min_spin, 1, 1)

        self._max_label = QLabel(tr("scan_max_size"), box)
        self._max_spin = QDoubleSpinBox(box)
        self._max_spin.setRange(0.0, 10240.0)
        self._max_spin.setSingleStep(1.0)
        self._max_spin.setDecimals(1)
        self._max_spin.setSuffix(" MB")
        grid.addWidget(self._max_label, 2, 0)
        grid.addWidget(self._max_spin, 2, 1)

        self._excluded_label = QLabel(tr("scan_excluded_folders"), box)
        self._excluded_edit = QLineEdit(box)
        self._excluded_edit.setPlaceholderText("Windows; Program Files; $Recycle.Bin")
        grid.addWidget(self._excluded_label, 3, 0)
        grid.addWidget(self._excluded_edit, 3, 1)

        # Column 1 holds the editable fields and must absorb the free width.
        # (Column 2 was a phantom stretch column that, under RTL, swallowed the
        #  space on the *left* and squeezed the fields against the labels.)
        grid.setColumnStretch(0, 0)
        grid.setColumnStretch(1, 1)
        return box

    def _build_progress(self, parent) -> QFrame:
        frame = QFrame(parent)
        frame.setObjectName("Card")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(10)

        header = QHBoxLayout()
        header.setSpacing(12)
        self._stage_label = QLabel(tr("status_ready"), frame)
        self._stage_label.setObjectName("PageSubtitle")
        self._percent_label = QLabel("0%", frame)
        self._percent_label.setObjectName("PageSubtitle")
        self._elapsed_label = QLabel("", frame)
        self._elapsed_label.setObjectName("DimLabel")
        header.addWidget(self._stage_label)
        header.addStretch()
        header.addWidget(self._percent_label)
        header.addWidget(self._elapsed_label)
        layout.addLayout(header)

        self._overall_bar = self._make_bar(frame)
        self._overall_bar.setRange(0, 100)
        layout.addWidget(self._overall_bar)

        self._stage_bar = self._make_bar(frame)
        layout.addWidget(self._stage_bar)

        details = QGridLayout()
        details.setHorizontalSpacing(24)
        details.setVerticalSpacing(6)
        self._files_value = QLabel("0", frame)
        self._images_value = QLabel("0", frame)
        self._current_value = QLabel("", frame)
        self._eta_value = QLabel("--", frame)
        self._rate_value = QLabel("", frame)
        self._files_label = QLabel(tr("scan_files_scanned"), frame)
        self._images_label = QLabel(tr("scan_images_found"), frame)
        self._current_label = QLabel(tr("scan_current"), frame)
        self._eta_label = QLabel(tr("scan_time_remaining"), frame)
        self._current_label = QLabel(tr("scan_current"), frame)
        self._eta_label = QLabel(tr("scan_time_remaining"), frame)
        self._rate_label = QLabel(tr("scan_progress"), frame)
        for column, (label, value) in enumerate(
            (
                (self._files_label, self._files_value),
                (self._images_label, self._images_value),
                (self._eta_label, self._eta_value),
                (self._rate_label, self._rate_value),
            )
        ):
            label.setObjectName("DimLabel")
            details.addWidget(label, 0, column)
            details.addWidget(value, 1, column)
        self._current_label.setObjectName("DimLabel")
        details.addWidget(self._current_label, 2, 0, 1, 4)
        details.addWidget(self._current_value, 3, 0, 1, 4)
        layout.addLayout(details)

        actions = QHBoxLayout()
        actions.setSpacing(10)
        self._btn_start = QPushButton(tr("scan_start"), frame)
        self._btn_start.setMinimumHeight(42)
        self._btn_pause = QPushButton(tr("scan_pause"), frame)
        self._btn_pause.setObjectName("SecondaryButton")
        self._btn_pause.setMinimumHeight(42)
        self._btn_cancel = QPushButton(tr("scan_cancel"), frame)
        self._btn_cancel.setObjectName("DangerButton")
        self._btn_cancel.setMinimumHeight(42)
        self._btn_start.clicked.connect(self.start_scan)
        self._btn_pause.clicked.connect(self._toggle_pause)
        self._btn_cancel.clicked.connect(self.cancel_scan)
        actions.addWidget(self._btn_start)
        actions.addWidget(self._btn_pause)
        actions.addWidget(self._btn_cancel)
        actions.addStretch()
        layout.addLayout(actions)

        self._set_running(False)
        return frame

    @staticmethod
    def _make_bar(parent) -> QProgressBar:
        from PySide6.QtWidgets import QProgressBar

        bar = QProgressBar(parent)
        bar.setRange(0, 100)
        bar.setValue(0)
        # Win11 progress bars are slim pills; the percentage lives in the header.
        bar.setTextVisible(False)
        return bar

    # ------------------------------------------------------------------
    # Target handling
    # ------------------------------------------------------------------

    def _target_changed(self) -> None:
        target = self._combo_targets.currentData()
        self._folder_frame.setVisible(target == "folders")
        self._drive_frame.setVisible(target == "removable")

    def _reload_drives(self) -> None:
        self._drive_list.clear()
        try:
            drives = system_info.list_drives()
        except Exception as exc:
            _log.warning("Cannot enumerate drives: %s", exc)
            drives = []
        removable = [drive for drive in drives if drive.is_removable]
        for drive in removable or drives:
            text = f"{drive.letter}  {drive.label}  ({format_size(drive.total_bytes)})"
            item = QListWidgetItem(text)
            item.setData(Qt.UserRole, drive.letter)
            item.setCheckState(Qt.Checked)
            self._drive_list.addItem(item)
        if self._drive_list.count() == 0:
            item = QListWidgetItem(tr("results_unavailable"))
            item.setFlags(item.flags() & ~Qt.ItemIsEnabled)
            self._drive_list.addItem(item)

    def _restore_folders(self) -> None:
        folders = self._context.config.last_scan_folders or []
        for folder in folders:
            self._folder_list.addItem(folder)
        scan = self._context.config.scan
        self._check_hidden.setChecked(scan.include_hidden_files)
        self._min_spin.setValue(scan.min_file_size_mb)
        self._max_spin.setValue(scan.max_file_size_mb)
        self._excluded_edit.setText("; ".join(scan.excluded_folders))

    def _refresh_profiles(self, selected_name: Optional[str] = None) -> None:
        self._profile_combo.blockSignals(True)
        self._profile_combo.clear()
        self._profile_combo.addItem(tr("scan_profile_choose"), "")
        for name in sorted(self._context.config.scan_profiles, key=str.casefold):
            self._profile_combo.addItem(name, name)
        index = self._profile_combo.findData(selected_name or "")
        self._profile_combo.setCurrentIndex(max(0, index))
        self._profile_combo.blockSignals(False)
        has_profile = bool(self._context.config.scan_profiles)
        self._btn_delete_profile.setEnabled(has_profile and bool(selected_name))

    def _profile_data(self) -> dict:
        return {
            "target": self._combo_targets.currentData(),
            "folders": self._selected_folders(),
            "drive_roots": self._selected_drive_roots(),
            "include_hidden_files": self._check_hidden.isChecked(),
            "min_file_size_mb": self._min_spin.value(),
            "max_file_size_mb": self._max_spin.value(),
            "excluded_folders": [
                part.strip()
                for part in self._excluded_edit.text().split(";")
                if part.strip()
            ],
        }

    def _save_profile(self) -> None:
        current = self._profile_combo.currentData() or ""
        name, accepted = QInputDialog.getText(
            self, tr("scan_profile_save"), tr("scan_profile_name"), text=current
        )
        name = name.strip()
        if not accepted or not name:
            return
        if name in self._context.config.scan_profiles and name != current:
            answer = QMessageBox.question(
                self, tr("scan_profile_save"), tr("scan_profile_overwrite", name=name)
            )
            if answer != QMessageBox.Yes:
                return
        self._context.config.scan_profiles[name] = self._profile_data()
        self._context.save_config()
        self._refresh_profiles(name)

    def _delete_profile(self) -> None:
        name = self._profile_combo.currentData()
        if not name:
            return
        answer = QMessageBox.question(
            self, tr("scan_profile_delete"), tr("scan_profile_delete_confirm", name=name)
        )
        if answer != QMessageBox.Yes:
            return
        self._context.config.scan_profiles.pop(name, None)
        self._context.save_config()
        self._refresh_profiles()

    def _load_selected_profile(self, _index: int = -1) -> None:
        name = self._profile_combo.currentData()
        self._btn_delete_profile.setEnabled(bool(name))
        if not name:
            return
        profile = self._context.config.scan_profiles.get(name)
        if not isinstance(profile, dict):
            return
        target_index = self._combo_targets.findData(profile.get("target"))
        if target_index >= 0:
            self._combo_targets.setCurrentIndex(target_index)
        self._folder_list.clear()
        folders = profile.get("folders", [])
        if not isinstance(folders, list):
            folders = []
        for folder in folders:
            if isinstance(folder, str):
                self._folder_list.addItem(folder)
        drive_roots = profile.get("drive_roots", [])
        wanted_drives = set(drive_roots) if isinstance(drive_roots, list) else set()
        for row in range(self._drive_list.count()):
            item = self._drive_list.item(row)
            root = item.data(Qt.UserRole)
            if root:
                item.setCheckState(Qt.Checked if root in wanted_drives else Qt.Unchecked)
        self._check_hidden.setChecked(bool(profile.get("include_hidden_files", False)))
        self._min_spin.setValue(self._safe_float(profile.get("min_file_size_mb"), 0.0))
        self._max_spin.setValue(self._safe_float(profile.get("max_file_size_mb"), 0.0))
        excluded = profile.get("excluded_folders", [])
        if not isinstance(excluded, list):
            excluded = []
        self._excluded_edit.setText("; ".join(str(item) for item in excluded if item))
        self._target_changed()

    @staticmethod
    def _safe_float(value, default: float) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    def _add_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, tr("scan_add_folder"))
        if not folder:
            return
        existing = [
            self._folder_list.item(row).text() for row in range(self._folder_list.count())
        ]
        if folder in existing:
            return
        self._folder_list.addItem(folder)

    def _remove_folder(self) -> None:
        for item in self._folder_list.selectedItems():
            self._folder_list.takeItem(self._folder_list.row(item))

    def _selected_folders(self) -> List[str]:
        return [
            self._folder_list.item(row).text() for row in range(self._folder_list.count())
        ]

    def _selected_drive_roots(self) -> List[str]:
        roots = []
        for row in range(self._drive_list.count()):
            item = self._drive_list.item(row)
            if item.checkState() == Qt.Checked:
                root = item.data(Qt.UserRole)
                if root:
                    roots.append(root)
        return roots

    # ------------------------------------------------------------------
    # Scan lifecycle
    # ------------------------------------------------------------------

    def _apply_options(self) -> None:
        scan = self._context.config.scan
        scan.include_hidden_files = self._check_hidden.isChecked()
        scan.min_file_size_mb = self._min_spin.value()
        scan.max_file_size_mb = self._max_spin.value()
        excluded = [
            part.strip()
            for part in self._excluded_edit.text().split(";")
            if part.strip()
        ]
        scan.excluded_folders = excluded
        self._context.save_config()

    def start_scan(self) -> None:
        if self._worker is not None and self._worker.isRunning():
            return

        self._apply_options()
        target = self._combo_targets.currentData()

        worker = ScanWorker(
            database=self._context.database,
            config=self._context.config,
            folders=self._selected_folders(),
            scan_drives=(target in ("drives", "removable")),
            include_removable=(target == "removable"),
        )
        if target == "removable":
            roots = self._selected_drive_roots()
            if not roots:
                QMessageBox.information(self, tr("nav_scan"), tr("results_unavailable"))
                return
            worker.folders = roots
            worker.scan_drives = False

        worker.progress.connect(self._on_progress)
        worker.stage_changed.connect(self._on_stage_changed)
        worker.finished_scan.connect(self._on_finished)
        worker.failed.connect(self._on_failed)
        self._worker = worker
        self._context.config.last_scan_folders = self._selected_folders()
        self._context.save_config()

        self._set_running(True)
        self._reset_progress()
        self.scan_started.emit()
        worker.start()

    def _toggle_pause(self) -> None:
        if self._worker is None:
            return
        if self._worker.is_paused:
            self._worker.resume()
            self._btn_pause.setText(tr("scan_pause"))
        else:
            self._worker.pause()
            self._btn_pause.setText(tr("scan_resume"))

    def cancel_scan(self) -> None:
        if self._worker is None:
            return
        self._worker.cancel()

    def is_scanning(self) -> bool:
        return self._worker is not None and self._worker.isRunning()

    def _set_running(self, running: bool) -> None:
        self._btn_start.setEnabled(not running)
        self._btn_pause.setEnabled(running)
        self._btn_cancel.setEnabled(running)
        self._combo_targets.setEnabled(not running)
        self._profile_combo.setEnabled(not running)
        self._btn_save_profile.setEnabled(not running)
        self._btn_delete_profile.setEnabled(not running and bool(self._profile_combo.currentData()))
        self._btn_add.setEnabled(not running)
        self._btn_remove.setEnabled(not running)

    def _reset_progress(self) -> None:
        self._overall_bar.setValue(0)
        self._stage_bar.setValue(0)
        self._percent_label.setText("0%")
        self._files_value.setText("0")
        self._images_value.setText("0")
        self._current_value.setText("")
        self._eta_value.setText("--")
        self._rate_value.setText("")
        self._elapsed_label.setText("")

    # ------------------------------------------------------------------
    # Worker signals
    # ------------------------------------------------------------------

    def _on_stage_changed(self, stage: str) -> None:
        self._stage_label.setText(tr(f"scan_stage_{stage}", default=stage))

    def _on_progress(self, update: ProgressUpdate) -> None:
        self._overall_bar.setValue(int(update.overall_progress))
        self._percent_label.setText(f"{int(update.overall_progress)}%")
        self._stage_bar.setValue(int(update.stage_progress))
        self._files_value.setText(f"{update.files_scanned:,}")
        self._images_value.setText(f"{update.images_found:,}")
        self._current_value.setText(update.current_path)
        self._eta_value.setText(update.eta_label)
        if update.rate > 0:
            self._rate_label.setText(tr("scan_progress"))
            self._rate_value.setText(f"{update.rate:.0f}/s")
        if update.message:
            self._stage_label.setText(update.message)
        self._elapsed_label.setText(format_duration(update.elapsed_seconds))

    def _on_finished(self, result) -> None:
        self._set_running(False)
        self._btn_pause.setText(tr("scan_pause"))
        session: Optional[ScanSession] = getattr(result, "session", None)
        status = getattr(result, "status", None)
        if status is not None and str(status.value) == "completed":
            self._stage_label.setText(tr("status_done"))
            self._overall_bar.setValue(100)
        else:
            self._stage_label.setText(tr("scan_stage_cancelled"))
        self.scan_finished.emit(result)

    def _on_failed(self, message: str) -> None:
        self._set_running(False)
        self._stage_label.setText(tr("scan_stage_failed"))
        _log.error("Scan failed: %s", message)
        QMessageBox.critical(self, tr("scan_stage_failed"), message)

    # ------------------------------------------------------------------
    # Retranslation
    # ------------------------------------------------------------------

    def retranslate(self) -> None:
        self._title.setText(tr("nav_scan"))
        self._subtitle.setText(tr("app_tagline"))
        self._combo_targets.setItemText(0, tr("scan_entire_computer"))
        self._combo_targets.setItemText(1, tr("scan_usb_drives"))
        self._combo_targets.setItemText(2, tr("scan_select_folder"))
        self._btn_add.setText(tr("scan_add_folder"))
        self._btn_remove.setText(tr("scan_remove"))
        self._btn_save_profile.setText(tr("scan_profile_save"))
        self._btn_delete_profile.setText(tr("scan_profile_delete"))
        selected_profile = self._profile_combo.currentData()
        self._refresh_profiles(selected_profile)
        self._check_hidden.setText(tr("scan_include_hidden"))
        self._min_label.setText(tr("scan_min_size"))
        self._max_label.setText(tr("scan_max_size"))
        self._excluded_label.setText(tr("scan_excluded_folders"))
        self._files_label.setText(tr("scan_files_scanned"))
        self._images_label.setText(tr("scan_images_found"))
        self._current_label.setText(tr("scan_current"))
        self._eta_label.setText(tr("scan_time_remaining"))
        if not self.is_scanning():
            self._stage_label.setText(tr("status_ready"))
            self._btn_start.setText(tr("scan_start"))
            self._btn_pause.setText(tr("scan_pause"))
            self._btn_cancel.setText(tr("scan_cancel"))
